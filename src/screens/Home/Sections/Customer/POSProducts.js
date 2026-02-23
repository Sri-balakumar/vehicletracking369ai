import React, { useEffect, useCallback } from 'react';
import { View } from 'react-native';
import { NavigationHeader } from '@components/Header';
import { ProductsList } from '@components/Product';
import { fetchProductsOdoo } from '@api/services/generalApi';
import { useIsFocused, useFocusEffect } from '@react-navigation/native';
import { FlashList } from '@shopify/flash-list';
import { formatData } from '@utils/formatters';
import { OverlayLoader } from '@components/Loader';
import { RoundedContainer, SafeAreaView, SearchContainer } from '@components/containers';
import { COLORS } from '@constants/theme';
import styles from './styles';
import { EmptyState } from '@components/common/empty';
import useDataFetching from '@hooks/useDataFetching';
import useDebouncedSearch from '@hooks/useDebouncedSearch';
import { useProductStore } from '@stores/product';
import Toast from 'react-native-toast-message';
import { Button } from '@components/common/Button';

const POSProducts = ({ navigation, route }) => {
  const { openingAmount } = route?.params || {};
  const categoryId = '';
  const isFocused = useIsFocused();
  const { data, loading, fetchData, fetchMoreData } = useDataFetching(fetchProductsOdoo);
  const { searchText, handleSearchTextChange } = useDebouncedSearch(
    (text) => fetchData({ searchText: text, categoryId }),
    500
  );
  const { addProduct, setCurrentCustomer, clearProducts } = useProductStore();

  useFocusEffect(
    useCallback(() => {
      // Ensure POS cart owner
      setCurrentCustomer('pos_guest');
      fetchData({ searchText, categoryId });
    }, [searchText, categoryId])
  );

  useEffect(() => {
    if (isFocused) fetchData({ searchText, categoryId });
  }, [isFocused, searchText, categoryId]);

  const handleLoadMore = () => fetchMoreData({ searchText, categoryId });

  const handleAdd = (p) => {
    const product = {
      id: p.id,
      name: p.product_name || p.name,
      price: p.price || p.list_price || 0,
      quantity: 1,
      imageUrl: p.imageUrl || p.image_url || p.image || '',
    };
    addProduct(product);
    Toast.show({ type: 'success', text1: 'Added', text2: product.name });
  };

  const renderItem = ({ item }) => {
    if (item.empty) return <View style={[styles.itemStyle, styles.itemInvisible]} />;
    return (
      <ProductsList
        item={item}
        onPress={() => navigation.navigate('ProductDetail', { detail: item, fromPOS: true })}
        showQuickAdd
        onQuickAdd={handleAdd}
      />
    );
  };

  const renderEmptyState = () => (
    <EmptyState imageSource={require('@assets/images/EmptyData/empty_data.png')} message={''} />
  );

  const renderContent = () => (
    <FlashList
      data={formatData(data, 3)}
      numColumns={3}
      renderItem={renderItem}
      keyExtractor={(item, index) => index.toString()}
      contentContainerStyle={{ padding: 10, paddingBottom: 50 }}
      onEndReached={handleLoadMore}
      showsVerticalScrollIndicator={false}
      onEndReachedThreshold={0.2}
      estimatedItemSize={100}
    />
  );

  const renderProducts = () => {
    if (data.length === 0 && !loading) return renderEmptyState();
    return renderContent();
  };

  return (
    <SafeAreaView>
      <NavigationHeader title="Products" onBackPress={() => navigation.goBack()} />
      <SearchContainer placeholder="Search Products" onChangeText={handleSearchTextChange} value={searchText} />
      <RoundedContainer>
        {renderProducts()}
      </RoundedContainer>
      <View style={{ padding: 12, backgroundColor: COLORS.white }}>
        <OverlayLoader visible={loading} />
        <View style={{ marginTop: 12 }}>
          <Button
            title="View Cart"
            onPress={() => navigation.navigate('POSCartSummary', {
              openingAmount,
              clearCart: clearProducts
            })}
          />
        </View>
      </View>
    </SafeAreaView>
  );
};

export default POSProducts;
