import React, { useState, useEffect } from 'react';
import { View, StyleSheet, Image, ActivityIndicator, TouchableOpacity } from 'react-native';
import Text from '@components/Text';
import { FONT_FAMILY } from '@constants/theme';

const CategoryList = ({ item, onPress }) => {

    const errorImage = require('@assets/images/error/error.png');
    useEffect(() => {
        const timeout = setTimeout(() => {
            // Stop the loading indicator after a timeout (e.g., 10 seconds)
            setImageLoading(false);
        }, 10000); // Adjust the timeout as needed

        return () => clearTimeout(timeout);
    }, []);

    const [imageLoading, setImageLoading] = useState(true);
    return (
        <TouchableOpacity onPress={onPress} style={styles.container}>
            {item?.sequence_no !== null && item?.sequence_no !== undefined && (
                <View style={styles.seqBadge}>
                    <Text style={styles.seqText}>{item.sequence_no}</Text>
                </View>
            )}
            {imageLoading && <ActivityIndicator size="small" color={'black'} style={{ position: 'absolute', top: 30 }} />}
            <Image
                source={item?.image_url ? { uri: item.image_url } : errorImage}
                style={styles.image}
                onLoad={() => setImageLoading(false)}
                onError={() => setImageLoading(false)}
            />
            <View style={{ paddingTop: 50 }} />
            <View style={styles.textContainer}>
                <Text style={styles.name} numberOfLines={2}>{item?.category_name}</Text>
            </View>
        </TouchableOpacity>
    );
};

export default CategoryList;

const styles = StyleSheet.create({
    container: {
        flex: 1,
        alignItems: 'center',
        margin: 6,
        borderWidth: 0.5,
        borderRadius: 10,
        marginTop: 5,
        borderColor: 'grey',
        backgroundColor: "white",
    },
    image: {
        width: 80,
        height: 80,
        resizeMode: 'cover',
        borderRadius: 8,
        marginTop: 10,
    },
    textContainer: {
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        bottom: -80,
        justifyContent: 'center',
        alignItems: 'center',
    },
    name: {
        fontSize: 14,
        textAlign: 'center',
        textTransform: 'capitalize',
        color: '#1316c5ff',
        fontFamily: FONT_FAMILY.urbanistBold
    },
    seqBadge: {
        position: 'absolute',
        top: 6,
        left: 6,
        backgroundColor: '#1316c5ff',
        borderRadius: 10,
        minWidth: 20,
        height: 20,
        justifyContent: 'center',
        alignItems: 'center',
        paddingHorizontal: 4,
        zIndex: 1,
    },
    seqText: {
        fontSize: 10,
        color: '#fff',
        fontFamily: FONT_FAMILY.urbanistBold,
    },
});
