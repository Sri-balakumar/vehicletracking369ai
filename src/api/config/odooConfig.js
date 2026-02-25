// src/api/odooConfig.js

// 🔹 Put your Odoo server URL here ONE time
// Current test server
const ODOO_BASE_URL = "http://115.246.240.218:369";

// Default DB to use for Odoo JSON-RPC login (change to your test DB)
const DEFAULT_ODOO_DB = "shan1";

// Default test credentials for autofill (development only)
const DEFAULT_USERNAME = "admin";  // Add your test username here
const DEFAULT_PASSWORD = "admin";  // Add your test password here

// Named export for default base URL for backward compatibility
const DEFAULT_ODOO_BASE_URL = ODOO_BASE_URL;

export { DEFAULT_ODOO_DB, DEFAULT_ODOO_BASE_URL, DEFAULT_USERNAME, DEFAULT_PASSWORD };
export default ODOO_BASE_URL;
