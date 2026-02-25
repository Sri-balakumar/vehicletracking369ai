// src/screens/Auth/LoginScreenOdoo.js
import React, { useState } from "react";
import {
  View,
  Keyboard,
  StyleSheet,
  Image,
  TouchableWithoutFeedback,
  Alert,
  Linking,
  Platform,
} from "react-native";
import { COLORS, FONT_FAMILY } from "@constants/theme";
import { LogBox } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Button } from "@components/common/Button";
import { OverlayLoader } from "@components/Loader";
import axios from "axios";
// Removed expo-cookie import
import { post } from "@api/services/utils";
import { useNavigation } from "@react-navigation/native";
import Text from "@components/Text";
import { TextInput } from "@components/common/TextInput";
import { RoundedScrollContainer, SafeAreaView } from "@components/containers";
import { useAuthStore } from "@stores/auth";
import { showToastMessage } from "@components/Toast";
import { Checkbox } from "react-native-paper";
// ⚠️ Note: Background location tracking is disabled in Expo Go (requires dev build)
import { startLocationTracking } from "@services/LocationTrackingService";
import * as Location from 'expo-location';

import API_BASE_URL from "@api/config";
import ODOO_DEFAULTS, { DEFAULT_ODOO_BASE_URL, DEFAULT_ODOO_DB, DEFAULT_USERNAME, DEFAULT_PASSWORD } from "@api/config/odooConfig";
import { fetchCompanyCurrencyOdoo } from "@api/services/generalApi";
import { useCurrencyStore } from "@stores/currency";

LogBox.ignoreLogs(["new NativeEventEmitter"]);
LogBox.ignoreAllLogs();

// 🔍 Check if URL looks like an Odoo server (accepts ngrok, http(s) hosts, or typical Odoo paths)
const isOdooUrl = (url = "") => {
  const lower = url.toLowerCase();
  // Accept explicit protocols, ngrok hosts, or typical odoo paths
  return (
    lower.startsWith('http') ||
    lower.includes('ngrok') ||
    lower.includes('odoo') ||
    lower.includes('/web') ||
    lower.includes(':8069')
  );
};

const LoginScreenOdoo = () => {
  const navigation = useNavigation();
  const setUser = useAuthStore((state) => state.login);
  const setCurrencyFromOdoo = useCurrencyStore((state) => state.setCurrencyFromOdoo);
  const [checked, setChecked] = useState(false);
  const [autofillChecked, setAutofillChecked] = useState(false);

  const updateCheckedState = (value) => {
    setChecked(value);
  };

  const { container, imageContainer } = styles;

  LogBox.ignoreLogs([
    "Non-serializable values were found in the navigation state",
  ]);

  const [inputs, setInputs] = useState({
    baseUrl: "", // ✅ NEW: Server URL (optional)
    db: "",
    username: "",
    password: "",
  });
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);

  // Handle autofill checkbox toggle
  const handleAutofillToggle = () => {
    const newValue = !autofillChecked;
    setAutofillChecked(newValue);

    if (newValue) {
      // Autofill with defaults from odooConfig
      setInputs((prev) => ({
        ...prev,
        baseUrl: DEFAULT_ODOO_BASE_URL || prev.baseUrl,
        db: DEFAULT_ODOO_DB || prev.db,
        username: DEFAULT_USERNAME || prev.username,
        password: DEFAULT_PASSWORD || prev.password,
      }));
    } else {
      // Clear fields when unchecked
      setInputs({
        baseUrl: "",
        db: "",
        username: "",
        password: "",
      });
    }
  };

  const handleOnchange = (text, input) => {
    setInputs((prevState) => ({ ...prevState, [input]: text }));
  };

  const handleError = (error, input) => {
    setErrors((prevState) => ({ ...prevState, [input]: error }));
  };

  // Check if location services are enabled and permission is granted
  const checkLocationEnabled = async () => {
    try {
      // Check if location services are enabled on device
      const isLocationEnabled = await Location.hasServicesEnabledAsync();

      if (!isLocationEnabled) {
        Alert.alert(
          'Location Required',
          'Please turn on location services to login. This app requires location tracking.',
          [
            { text: 'Cancel', style: 'cancel' },
            {
              text: 'Open Settings',
              onPress: () => {
                if (Platform.OS === 'ios') {
                  Linking.openURL('app-settings:');
                } else {
                  Linking.openSettings();
                }
              }
            }
          ]
        );
        return false;
      }

      // Request location permission
      const { status } = await Location.requestForegroundPermissionsAsync();

      if (status !== 'granted') {
        Alert.alert(
          'Permission Required',
          'Location permission is required to login. Please grant location access.',
          [
            { text: 'Cancel', style: 'cancel' },
            {
              text: 'Open Settings',
              onPress: () => {
                if (Platform.OS === 'ios') {
                  Linking.openURL('app-settings:');
                } else {
                  Linking.openSettings();
                }
              }
            }
          ]
        );
        return false;
      }

      return true;
    } catch (error) {
      console.log('Location check error:', error);
      showToastMessage('Unable to check location status');
      return false;
    }
  };

  const validate = async () => {
    Keyboard.dismiss();
    let isValid = true;

    if (!inputs.username) {
      handleError("Please input user name", "username");
      isValid = false;
    }
    if (!inputs.password) {
      handleError("Please input password", "password");
      isValid = false;
    }
    if (!checked) {
      showToastMessage("Please agree Privacy Policy");
      isValid = false;
    }

    if (isValid) {
      // Check location before proceeding with login
      const locationEnabled = await checkLocationEnabled();
      if (locationEnabled) {
        login();
      }
    }
  };

  const login = async () => {
    setLoading(true);
    try {
      const baseUrlRaw = inputs.baseUrl || "";
      const baseUrl = baseUrlRaw.trim();
      const username = inputs.username;
      const password = inputs.password;

      const useOdoo = baseUrl && isOdooUrl(baseUrl);

      if (useOdoo) {
        // Use /api/login only. Do not fallback to /web/session/authenticate
        const normalized = baseUrl.startsWith('http') ? baseUrl : `https://${baseUrl}`;
        // Fix cases where port is provided with a dot instead of a colon,
        // e.g. 115.246.240.218.9169 -> 115.246.240.218:9169
        const fixed = normalized.replace(/(\d+\.\d+\.\d+\.\d+)\.(\d+)(\/.*)?$/, '$1:$2$3');
        const finalOdooUrl = (fixed.replace(/\/+$/, "") || DEFAULT_ODOO_BASE_URL);
        console.log('Using Odoo URL:', finalOdooUrl);
        const dbNameUsed = inputs.db && inputs.db.trim() ? inputs.db.trim() : DEFAULT_ODOO_DB;
        console.log('Logging in to Odoo DB:', dbNameUsed);
        let userData = null;
        let token = null;
        try {
          // Only try /api/login
          // Use /web/session/authenticate for Odoo login
          const odooLoginReqBody = {
            jsonrpc: "2.0",
            method: "call",
            params: {
              db: dbNameUsed,
              login: username,
              password: password,
            },
          };
          const odooLoginReqHeaders = {
            headers: {
              "Content-Type": "application/json",
            },
          };
          console.log("[REQ] /web/session/authenticate", {
            url: `${finalOdooUrl}/web/session/authenticate`,
            body: odooLoginReqBody,
            headers: odooLoginReqHeaders.headers,
          });
          const odooLoginRes = await axios.post(
            `${finalOdooUrl}/web/session/authenticate`,
            odooLoginReqBody,
            odooLoginReqHeaders
          );
          console.log("[RES] /web/session/authenticate", JSON.stringify(odooLoginRes.data, null, 2));
          const result = odooLoginRes.data && odooLoginRes.data.result;
          if (result && result.uid) {
            userData = result;
            // Persist DB and user info
            await AsyncStorage.setItem('odoo_db', dbNameUsed);
            await AsyncStorage.setItem("userData", JSON.stringify(userData));
            // Persist Set-Cookie header if available so other services can reuse session
            try {
              const setCookie = odooLoginRes.headers['set-cookie'] || odooLoginRes.headers['Set-Cookie'];
              if (setCookie) {
                const cookieStr = Array.isArray(setCookie) ? setCookie.join('; ') : String(setCookie);
                await AsyncStorage.setItem('odoo_cookie', cookieStr);
              }
            } catch (e) {
              console.warn('Unable to persist Odoo cookie header:', e?.message || e);
            }
            setUser(userData);
            // Fetch company currency from Odoo and update store
            try {
              const companyCurrency = await fetchCompanyCurrencyOdoo();
              if (companyCurrency) setCurrencyFromOdoo(companyCurrency);
            } catch (e) { console.warn('Could not fetch company currency:', e?.message); }
            // Start location tracking for non-admin users only
            // Check is_admin field from Odoo response
            if (userData.uid && !userData.is_admin) {
              startLocationTracking(userData.uid);
            }
            navigation.navigate("AppNavigator");
          } else {
            showToastMessage("Invalid Odoo credentials or login failed");
          }
        } catch (err) {
          showToastMessage("/web/session/authenticate failed: " + (err?.message || 'Unknown error'));
        }
      } else {
        // UAE ADMIN LOGIN
        const response = await post("/viewuser/login", {
          user_name: username,
          password: password,
        });
        console.log("🚀 UAE admin login response:", JSON.stringify(response, null, 2));
        if (response && response.success === true && response.data?.length) {
          const userData = response.data[0];
          await AsyncStorage.setItem("userData", JSON.stringify(userData));
          setUser(userData);
          // Start location tracking for non-admin UAE users
          if (userData._id && userData.user_name !== 'admin') {
            startLocationTracking(userData._id);
          }
          navigation.navigate("AppNavigator");
        } else {
          showToastMessage("Invalid admin credentials");
        }
      }
    } catch (error) {
      console.log("Login Error:", error.response ? error.response.data : error.message);
      showToastMessage(`Error! ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <TouchableWithoutFeedback onPress={() => Keyboard.dismiss()}>
      <SafeAreaView style={container}>
        <OverlayLoader visible={loading} />

        {/* Logo */}
        <View style={imageContainer}>
          <Image
            source={require("@assets/images/header/logo_header.png")}
            style={{ width: 300, height: 180, alignSelf: "center" }}
          />
        </View>

        <RoundedScrollContainer
          backgroundColor={COLORS.white}
          paddingHorizontal={15}
          borderTopLeftRadius={40}
          borderTopRightRadius={40}
        >
          <View style={{ paddingTop: 50 }}>
            <View style={{ marginVertical: 5, marginHorizontal: 10 }}>
              <View style={{ marginTop: 0, marginBottom: 15 }}>
                {/* Hints */}
                <Text
                  style={{
                    fontSize: 13,
                    fontFamily: FONT_FAMILY.urbanistSemiBold,
                    color: COLORS.grey,
                    textAlign: "center",
                    marginBottom: 5,
                  }}
                >
                  Leave Server URL empty to use UAE default:
                </Text>
                <Text
                  style={{
                    fontSize: 13,
                    fontFamily: FONT_FAMILY.urbanistBold,
                    color: COLORS.primaryThemeColor,
                    textAlign: "center",
                    marginBottom: 5,
                  }}
                >
                  {API_BASE_URL}
                </Text>
                <Text
                  style={{
                    fontSize: 12,
                    fontFamily: FONT_FAMILY.urbanistSemiBold,
                    color: COLORS.grey,
                    textAlign: "center",
                    marginBottom: 15,
                  }}
                >
                  For Odoo login, enter URL like: {DEFAULT_ODOO_BASE_URL}
                </Text>

                <Text
                  style={{
                    fontSize: 25,
                    fontFamily: FONT_FAMILY.urbanistBold,
                    color: "#2e2a4f",
                    textAlign: "center",
                  }}
                >
                  Login
                </Text>
              </View>

              {/* Server URL (optional) */}
              <TextInput
                value={inputs.baseUrl}
                onChangeText={(text) => handleOnchange(text, "baseUrl")}
                onFocus={() => handleError(null, "baseUrl")}
                label="Server URL (optional)"
                placeholder="https://486b3e7391ee.ngrok-free.app"
                column={true}
                login={true}
              />

              {/* Username */}
              <TextInput
                value={inputs.username}
                onChangeText={(text) => handleOnchange(text, "username")}
                onFocus={() => handleError(null, "username")}
                iconName="account-outline"
                label="Username or Email"
                placeholder="Enter Username or Email"
                error={errors.username}
                column={true}
                login={true}
              />

              {/* Password */}
              <TextInput
                value={inputs.password}
                onChangeText={(text) => handleOnchange(text, "password")}
                onFocus={() => handleError(null, "password")}
                error={errors.password}
                iconName="lock-outline"
                label="Password"
                placeholder="Enter password"
                password
                column={true}
                login={true}
              />

              {/* Privacy Policy */}
              <View
                style={{
                  flexDirection: "row",
                  alignItems: "center",
                  justifyContent: "flex-start",
                }}
              >
                <Checkbox
                  onPress={() =>
                    navigation.navigate("PrivacyPolicy", { updateCheckedState })
                  }
                  status={checked ? "checked" : "unchecked"}
                  color={COLORS.primaryThemeColor}
                />
                <Text
                  style={{
                    fontFamily: FONT_FAMILY.urbanistBold,
                    fontSize: 15,
                  }}
                >
                  I agree to the Privacy Policy
                </Text>
              </View>

              {/* Login Button */}
              <View style={styles.bottom}>
                <Button title="Login" onPress={validate} />
              </View>

              {/* Autofill Checkbox */}
              <View
                style={{
                  flexDirection: "row",
                  alignItems: "center",
                  justifyContent: "center",
                  marginTop: 15,
                }}
              >
                <Checkbox
                  onPress={handleAutofillToggle}
                  status={autofillChecked ? "checked" : "unchecked"}
                  color={COLORS.primaryThemeColor}
                />
                <Text
                  style={{
                    fontFamily: FONT_FAMILY.urbanistMedium,
                    fontSize: 14,
                    color: COLORS.grey,
                  }}
                >
                  Autofill test credentials
                </Text>
              </View>
            </View>
          </View>
        </RoundedScrollContainer>
      </SafeAreaView>
    </TouchableWithoutFeedback>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    paddingTop: 10,
  },
  tinyLogo: {
    width: 200,
    height: 200,
  },
  imageContainer: {
    alignItems: "center",
    marginBottom: "20%",
  },
  bottom: {
    alignItems: "center",
    marginTop: 10,
  },
  label: {
    marginVertical: 5,
    fontSize: 14,
    color: COLORS.grey,
    marginLeft: 180,
    marginTop: 15,
  },
});

export default LoginScreenOdoo;
