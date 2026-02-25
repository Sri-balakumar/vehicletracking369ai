/** @odoo-module **/

import { Component, useState, useRef, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/**
 * SignaturePadWidget
 *
 * An attractive inline signature widget that allows:
 *  - Drawing with adjustable pen (size + ink color)
 *  - Erasing with adjustable eraser
 *  - Uploading an image file
 *  - Clearing the canvas
 */
class SignaturePadWidget extends Component {
    static template = "auto_financial_auditing.SignaturePadWidget";
    static props = { ...standardFieldProps };

    setup() {
        this.canvasRef  = useRef("sigCanvas");
        this.fileRef    = useRef("fileInput");

        this.state = useState({
            tool:        "pen",     // "pen" | "eraser"
            penSize:     2,
            eraserSize:  20,
            penColor:    "#1a1a2e",
            isDrawing:   false,
            hasValue:    false,
        });

        this._lastX = 0;
        this._lastY = 0;

        onMounted(() => {
            this._initCanvas();
            if (this.props.record.data[this.props.name]) {
                this.state.hasValue = true;
                this._loadExistingValue();
            }
        });
    }

    // ── helpers ─────────────────────────────────────────────────────────────

    get fieldValue() {
        return this.props.record.data[this.props.name];
    }

    get cursorStyle() {
        if (this.props.readonly) return "default";
        return this.state.tool === "eraser" ? "cell" : "crosshair";
    }

    _initCanvas() {
        const canvas = this.canvasRef.el;
        if (!canvas) return;
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
    }

    _loadExistingValue() {
        const val = this.fieldValue;
        const id  = this.props.record.resId;
        const canvas = this.canvasRef.el;
        if (!canvas) return;

        let src = null;
        if (id && val) {
            src = `/web/image/${this.props.record.resModel}/${id}/${this.props.name}`;
        } else if (val && typeof val === "string") {
            src = `data:image/png;base64,${val}`;
        }
        if (!src) return;

        const img = new Image();
        img.onload = () => {
            const ctx = canvas.getContext("2d");
            ctx.fillStyle = "#ffffff";
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        };
        img.src = src;
    }

    _pos(e) {
        const canvas = this.canvasRef.el;
        const rect   = canvas.getBoundingClientRect();
        const sx     = canvas.width  / rect.width;
        const sy     = canvas.height / rect.height;
        const src    = e.touches ? e.touches[0] : e;
        return {
            x: (src.clientX - rect.left) * sx,
            y: (src.clientY - rect.top)  * sy,
        };
    }

    _saveToField() {
        const dataUrl = this.canvasRef.el.toDataURL("image/png");
        const b64     = dataUrl.split(",")[1];
        this.props.record.update({ [this.props.name]: b64 });
        this.state.hasValue = true;
    }

    // ── canvas events ────────────────────────────────────────────────────────

    onPointerDown(e) {
        if (this.props.readonly) return;
        this.state.isDrawing = true;
        const p = this._pos(e);
        this._lastX = p.x;
        this._lastY = p.y;
        if (e.pointerId !== undefined) {
            try { this.canvasRef.el.setPointerCapture(e.pointerId); } catch(_) {}
        }
        e.preventDefault();
    }

    onPointerMove(e) {
        if (!this.state.isDrawing || this.props.readonly) return;
        const canvas = this.canvasRef.el;
        const ctx    = canvas.getContext("2d");
        const p      = this._pos(e);

        ctx.beginPath();
        ctx.lineCap  = "round";
        ctx.lineJoin = "round";
        ctx.moveTo(this._lastX, this._lastY);
        ctx.lineTo(p.x, p.y);

        if (this.state.tool === "eraser") {
            ctx.globalCompositeOperation = "source-over";
            ctx.strokeStyle = "#ffffff";
            ctx.lineWidth   = this.state.eraserSize;
        } else {
            ctx.globalCompositeOperation = "source-over";
            ctx.strokeStyle = this.state.penColor;
            ctx.lineWidth   = this.state.penSize;
        }
        ctx.stroke();

        this._lastX = p.x;
        this._lastY = p.y;
        e.preventDefault();
    }

    onPointerUp() {
        if (!this.state.isDrawing) return;
        this.state.isDrawing = false;
        this._saveToField();
    }

    // ── toolbar actions ──────────────────────────────────────────────────────

    setTool(tool) {
        this.state.tool = tool;
    }

    onPenSizeChange(e) {
        this.state.penSize = parseInt(e.target.value, 10);
    }

    onEraserSizeChange(e) {
        this.state.eraserSize = parseInt(e.target.value, 10);
    }

    onColorChange(e) {
        this.state.penColor = e.target.value;
    }

    clearCanvas() {
        const canvas = this.canvasRef.el;
        const ctx    = canvas.getContext("2d");
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        this.state.tool    = "pen";
        this.state.hasValue = false;
        this.props.record.update({ [this.props.name]: false });
    }

    triggerUpload() {
        this.fileRef.el.click();
    }

    onFileChange(e) {
        const file = e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (evt) => {
            const canvas = this.canvasRef.el;
            const ctx    = canvas.getContext("2d");
            const img    = new Image();
            img.onload = () => {
                ctx.fillStyle = "#ffffff";
                ctx.fillRect(0, 0, canvas.width, canvas.height);
                ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
                this._saveToField();
            };
            img.src = evt.target.result;
        };
        reader.readAsDataURL(file);
        e.target.value = "";
    }
}

registry.category("fields").add("signature_pad", {
    component: SignaturePadWidget,
    supportedTypes: ["binary"],
});

export default SignaturePadWidget;
