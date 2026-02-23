import React, { useMemo, useState, useEffect, useCallback } from "react";
import {
  View,
  Dimensions,
  StyleSheet,
  ActivityIndicator,
  BackHandler,
} from "react-native";
import {
  CarouselPagination,
  ImageContainer,
  ListHeader,
  Header,
  NavigationBar,
} from "@components/Home";
import BottomSheet, { BottomSheetFlatList } from "@gorhom/bottom-sheet";
import { fetchCategoriesOdoo as fetchCategories } from "@api/services/generalApi";
import { RoundedContainer, SafeAreaView } from "@components/containers";
import { formatData } from "@utils/formatters";
import { COLORS } from "@constants/theme";
import { showToastMessage } from "@components/Toast";
import { CategoryList } from "@components/Categories";
import { useDataFetching, useLoader } from "@hooks";
import { useFocusEffect, useIsFocused } from "@react-navigation/native";
import { fetchProductDetailsByBarcode } from "@api/details/detailApi";
import { OverlayLoader } from "@components/Loader";

const { height } = Dimensions.get("window");

const HomeScreen = ({ navigation }) => {
  const [backPressCount, setBackPressCount] = useState(0);
  const isFocused = useIsFocused();
  const { data, loading, fetchData, fetchMoreData } =
    useDataFetching(fetchCategories);

  const handleBackPress = useCallback(() => {
    if (navigation.isFocused()) {
      if (backPressCount === 0) {
        setBackPressCount(1);
        return true;
      } else if (backPressCount === 1) {
        BackHandler.exitApp();
      }
    }
    return false; // Allow default back action
  }, [backPressCount, navigation]);

  useEffect(() => {
    const backHandler = BackHandler.addEventListener(
      "hardwareBackPress",
      handleBackPress
    );
    return () => backHandler.remove();
  }, [handleBackPress]);

  useEffect(() => {
    const backPressTimer = setTimeout(() => {
      setBackPressCount(0);
    }, 2000);

    return () => clearTimeout(backPressTimer);
  }, [backPressCount]);

  useEffect(() => {
    // Show toast message when backPressCount changes to 1
    if (backPressCount === 1) {
      showToastMessage("Press back again to exit");
    }
  }, [backPressCount]);

  useFocusEffect(
    useCallback(() => {
      fetchData();
    }, [])
  );

  useEffect(() => {
    if (isFocused) {
      fetchData();
    }
  }, [isFocused]);

  const handleLoadMore = () => {
    fetchMoreData();
  };

  const renderItem = ({ item }) => {
    if (item.empty) {
      return <View style={[styles.itemStyle, styles.itemInvisible]} />;
    }
    return (
      <CategoryList
        item={item}
        onPress={() => navigation.navigate("Products", { id: item._id })}
      />
    );
  };

  const navigateToScreen = (screenName) => {
    navigation.navigate(screenName);
  };

  // Define different snap points based on screen height
  const snapPoints = useMemo(() => {
    if (height < 700) {
      return ["33%", "79%"];
    } else if (height < 800) {
      return ["45%", "83%"];
    } else if (height < 810) {
      return ["45%", "83%"];
    } else {
      return ["50%", "85%"];
    }
  }, [height]);


  const [detailLoading, startLoading, stopLoading] = useLoader(false);

  const handleScan = async (code) => {
    startLoading();
    try {
      const productDetails = await fetchProductDetailsByBarcode(code);
      if (productDetails.length > 0) {
        const details = productDetails[0];
        navigation.navigate('ProductDetail', { detail: details })
      } else {
        showToastMessage("No Products found for this Barcode");
      }
    } catch (error) {
      showToastMessage(`Error fetching inventory details ${error.message}`);
    } finally {
      stopLoading();
    }
  };


  return (
    <SafeAreaView backgroundColor={COLORS.primaryThemeColor}>
      {/* rounded border */}
      <RoundedContainer>
        {/* Header */}
        <Header />
        {/* Navigation Header */}
        <NavigationBar
          onSearchPress={() => navigation.navigate("Products")}
          onOptionsPress={() => navigation.navigate("OptionsScreen")}
          onScannerPress={() => navigation.navigate("Scanner", { onScan: handleScan })}
        />
        {/* Carousel */}
        <CarouselPagination />

        {/* Section */}
        <View
          style={{
            flexDirection: "row",
            justifyContent: "space-between",
            marginHorizontal: 8,
          }}
        >
          <ImageContainer
            source={require("@assets/images/Home/section/inventory_management.png")}
            onPress={() => navigateToScreen("InventoryScreen")}
            backgroundColor="#f37021"
            title="INVMGT"
          />
          <ImageContainer
            source={require("@assets/images/Home/section/services.png")}
            onPress={() => navigateToScreen("ServicesScreen")}
            backgroundColor="#f37021"
            title="Services"
          />
          <ImageContainer
            source={require("@assets/images/Home/section/customer.png")}
            onPress={() => navigateToScreen("SalesOrderChoice")}
            backgroundColor="#f37021"
            title="Sales Order"
          />
        </View>

        {/* Bottom sheet */}
        <BottomSheet snapPoints={snapPoints}>
          {/* Product list header */}
          <ListHeader title="Categories" />
          {/* flatlist */}
          <BottomSheetFlatList
            data={formatData(data, 3)}
            numColumns={3}
            initialNumToRender={5}
            renderItem={renderItem}
            keyExtractor={(item, index) => index.toString()}
            contentContainerStyle={{ paddingBottom: "25%" }}
            onEndReached={handleLoadMore}
            showsVerticalScrollIndicator={false}
            onEndReachedThreshold={0.1}
            ListFooterComponent={
              loading && <ActivityIndicator size="large" color="#0000ff" />
            }
          />
        </BottomSheet>
        <OverlayLoader visible={detailLoading} />
      </RoundedContainer>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  itemInvisible: {
    backgroundColor: "transparent",
  },
  itemStyle: {
    flex: 1,
    alignItems: "center",
    margin: 6,
    borderRadius: 8,
    marginTop: 5,
    backgroundColor: "white",
  },
});

export default HomeScreen;
