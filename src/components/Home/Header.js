import React from 'react';
import { View, Image, StyleSheet, Dimensions } from 'react-native';

const { width } = Dimensions.get('window');

const Header = () => {
  return (
    <View style={styles.container}>
      <Image 
        source={require('@assets/images/Home/Header/header_transparent_bg.png')} 
        style={styles.backgroundImage} 
      />
      <Image 
        source={require('@assets/images/Home/Header/notification_2.png')} 
        style={styles.notificationIcon} 
      />
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 10,
    // Add any additional styles for the container if needed
  },
  backgroundImage: {
    width: width * 0.5,
    aspectRatio: 3,
    // Add any additional styles for the background image if needed
  },
  notificationIcon: {
    width: width * 0.25,
    aspectRatio: 3 / 1.3,
    resizeMode: 'contain',
    // Add any additional styles for the notification icon if needed
  }
});

export default Header;
