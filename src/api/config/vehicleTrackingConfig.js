// src/api/config/vehicleTrackingConfig.js

// 🔹 Put your Vehicle Tracking API base URL here
const VEHICLE_TRACKING_BASE_URL = "http://115.246.240.218:9169/";

// Database name for vehicle tracking
const DEFAULT_VEHICLE_TRACKING_DB = "test-vehicle";

// Named export for default base URL for backward compatibility
const DEFAULT_VEHICLE_TRACKING_BASE_URL = VEHICLE_TRACKING_BASE_URL;

export { DEFAULT_VEHICLE_TRACKING_BASE_URL, DEFAULT_VEHICLE_TRACKING_DB };
export default VEHICLE_TRACKING_BASE_URL;
