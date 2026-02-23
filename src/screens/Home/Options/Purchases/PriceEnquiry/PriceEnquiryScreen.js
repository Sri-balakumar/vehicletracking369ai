import React from 'react'
import { RoundedContainer, SafeAreaView } from '@components/containers';
import { EmptyState } from '@components/common/empty';
import { NavigationHeader } from '@components/Header';
import { FABButton } from '@components/common/Button';

const PriceEnquiryScreen = ({ navigation }) => {
  return (
    <SafeAreaView>
      <NavigationHeader
        title="Product Enquiry"
        onBackPress={() => navigation.goBack()}
      />
      <RoundedContainer>
        <EmptyState imageSource={require('@assets/images/EmptyData/empty.png')} message={'No Enquiries Yet'} />
        <FABButton onPress={() => navigation.navigate('PriceEnquiryForm')} />
      </RoundedContainer>
    </SafeAreaView>
  );
};

export default PriceEnquiryScreen;
