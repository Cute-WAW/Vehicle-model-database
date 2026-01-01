const app = getApp();

Page({
    data: {
        list: [],
        loading: false,
        total: 0
    },

    onShow() {
        this.loadHistory();
    },

    async loadHistory() {
        if (!app.globalData.token) {
            return;
        }

        this.setData({ loading: true });

        try {
            const result = await app.request({
                url: '/history',
                method: 'GET'
            });

            if (result.success) {
                this.setData({
                    list: result.items,
                    total: result.total
                });
            }
        } catch (e) {
            console.error('加载失败', e);
        } finally {
            this.setData({ loading: false });
        }
    },

    // 查看详情
    onItemTap(e) {
        const item = e.currentTarget.dataset.item;
        wx.navigateTo({
            url: `/pages/result/result?data=${encodeURIComponent(JSON.stringify({
                predicted_price: item.predicted_price,
                price_range: { low: item.price_low, high: item.price_high },
                explanation: item.explanation
            }))}&vehicle=${encodeURIComponent(item.vehicle_full_name)}`
        });
    },

    // 删除记录
    onDelete(e) {
        const id = e.currentTarget.dataset.id;

        wx.showModal({
            title: '确认删除',
            content: '确定要删除这条记录吗？',
            success: async (res) => {
                if (res.confirm) {
                    try {
                        await app.request({
                            url: `/history/${id}`,
                            method: 'DELETE'
                        });
                        this.loadHistory();
                        wx.showToast({ title: '已删除', icon: 'success' });
                    } catch (e) {
                        wx.showToast({ title: '删除失败', icon: 'none' });
                    }
                }
            }
        });
    }
});
