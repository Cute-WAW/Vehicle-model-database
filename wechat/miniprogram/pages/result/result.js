Page({
    data: {
        result: null,
        vehicleName: ''
    },

    onLoad(options) {
        if (options.data) {
            const result = JSON.parse(decodeURIComponent(options.data));
            this.setData({
                result: result,
                vehicleName: decodeURIComponent(options.vehicle || '')
            });
        }
    },

    // 复制结果
    onCopy() {
        const { result, vehicleName } = this.data;
        if (!result) return;

        const text = `【${vehicleName}】估价结果
预测价格: ${result.predicted_price}万元
价格区间: ${result.price_range.low}-${result.price_range.high}万元`;

        wx.setClipboardData({
            data: text,
            success: () => {
                wx.showToast({ title: '已复制', icon: 'success' });
            }
        });
    },

    // 重新估价
    onRetry() {
        wx.navigateBack();
    },

    // 返回首页
    onGoHome() {
        wx.switchTab({ url: '/pages/index/index' });
    }
});
