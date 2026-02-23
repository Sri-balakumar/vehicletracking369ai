import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { SafeAreaView } from '@components/containers';
import { NavigationHeader } from '@components/Header';
import { Button } from '@components/common/Button';

const POSRegister = ({ navigation }) => {
  return (
    <SafeAreaView style={styles.container}>
      <NavigationHeader title="POS Register" onBackPress={() => navigation.goBack()} />
      <View style={styles.centered}>
        <View style={styles.card}>
          <Text style={styles.icon}>🧾</Text>
          <Text style={styles.title}>Open Register</Text>
          <Text style={styles.subtitle}>Start a new POS register before taking orders.</Text>
          <Button title="Open Register" onPress={() => navigation.navigate('POSOpenAmount')} style={styles.openBtn} textStyle={{ fontSize: 18 }} />
        </View>
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#fff' },
  centered: { flex: 1, justifyContent: 'flex-start', alignItems: 'center', paddingHorizontal: 12, paddingTop: 40 },
  card: { backgroundColor: '#fff', padding: 40, borderRadius: 18, alignItems: 'center', shadowColor: '#000', shadowOpacity: 0.08, shadowRadius: 12, elevation: 6, width: '95%', minHeight: 420 },
  icon: { fontSize: 64, marginBottom: 16, color: '#2b6cb0' },
  title: { fontSize: 26, fontWeight: '700', marginTop: 8, color: '#222' },
  subtitle: { color: '#444', marginTop: 12, marginBottom: 22, textAlign: 'center', fontSize: 18 },
  openBtn: { marginTop: 18, width: '95%', paddingVertical: 14, borderRadius: 12 },
});

export default POSRegister;
