import React, {useState} from "react";
import { View, Text, Image } from "react-native";
import { MaterialIcons } from "@expo/vector-icons";
import { ButtonContainer, SafeAreaView } from "@components/containers";
import { Button } from "@components/common/Button";
import { COLORS, FONT_FAMILY } from "@constants/theme";
import { useAuthStore } from '@stores/auth';
import AsyncStorage from "@react-native-async-storage/async-storage";
import { LogoutModal } from "@components/Modal";

const ProfileScreen = ({navigation}) => {
  const userDetails = useAuthStore(state => state.user);

  const [isVisible, setIsVisible] = useState(false);
  const hideLogoutAlert = () => setIsVisible(false);

  const handleLogout = async () => {
    try {
      await AsyncStorage.removeItem('userData');
      const userData = await AsyncStorage.getItem('userData');
      navigation.reset({
        index: 0,
        routes: [{ name: 'Splash' }],
      });
      if (!userData) {
        console.log('User data successfully removed.');
        hideLogoutAlert();
      } else {
        console.log('User data still exists in AsyncStorage:', userData);
      }
    } catch (error) {
      console.error('Error logging out:', error);
    } finally {
      hideLogoutAlert();
    }
  };

  return (
    <SafeAreaView backgroundColor={COLORS.primaryThemeColor}>
      <View style={{ width: "100%" }}>
        <Image
          source={require('@assets/images/Profile/profile_bg.png')}
          resizeMode="cover"
          style={{ height: 300, width: "100%" }}
        />
      </View>
      <View style={{ flex: 1, alignItems: "center", backgroundColor: 'white', flex: 1, borderTopLeftRadius: 15, borderTopRightRadius: 15 }}>
        <Image
          source={require('@assets/images/Profile/user.png')}
          resizeMode="contain"
          style={{ height: 155, width: 155, borderWidth: 2, marginTop: -80 }}
        />

        <Text style={{ fontSize: 30, fontFamily: FONT_FAMILY.urbanistBold, color: '#242760', marginVertical: 8 }}>
          {userDetails?.related_profile?.name || userDetails?.user_name || 'N/A'}
        </Text>
        <Text style={{ color: COLORS.black, fontSize: 20, fontFamily: FONT_FAMILY.urbanistSemiBold }}>
          {userDetails?.company?.name?.toUpperCase() || 'N/A'}
        </Text>

        <View style={{ flexDirection: "row", marginVertical: 6, alignItems: "center" }}>
          <MaterialIcons name="location-on" size={24} color="black" />
          <Text style={{ fontSize: 14, fontFamily: FONT_FAMILY.urbanistSemiBold, marginLeft: 4 }}>
            {'N/A'}
          </Text>
        </View>
        <ButtonContainer>
          <Button paddingHorizontal={50} title={'LOGOUT'} onPress={() => setIsVisible(true)} />
        </ButtonContainer>
      </View>
      <LogoutModal
        isVisible={isVisible}
        hideLogoutAlert={hideLogoutAlert}
        handleLogout={handleLogout}
      />
    </SafeAreaView>
  );
};

export default ProfileScreen;
