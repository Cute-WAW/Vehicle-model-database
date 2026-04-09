const app = getApp();

Page({
    data: {
        // 表单数据
        vehicleFullName: '',
        brandSeries: '',
        years: 5,
        mileage: '',
        grade: '中',
        newPrice: '',
        city: '',

        // 状态
        loading: false,
        loggedIn: false
    },

    onLoad() {
        // 检查登录状态
        if (app.globalData.token) {
            this.setData({ loggedIn: true });
        }
    },

    onShow() {
        // 每次显示时检查登录
        if (!app.globalData.token) {
            this.autoLogin();
        } else {
            this.setData({ loggedIn: true });
        }
    },

    // 自动登录
    async autoLogin() {
        try {
            await app.loginWithEnvironment();
            this.setData({ loggedIn: true });
            wx.showToast({ title: '登录成功', icon: 'success' });
        } catch (e) {
            console.error('登录失败', e);
            wx.showToast({ title: '登录失败', icon: 'none' });
        }
    },

    // 输入处理
    onInputChange(e) {
        const { field } = e.currentTarget.dataset;
        this.setData({
            [field]: e.detail.value
        });
    },

    // 滑动条
    onSliderChange(e) {
        this.setData({
            years: e.detail.value
        });
    },

    // 评级选择
    onGradeSelect(e) {
        this.setData({
            grade: e.currentTarget.dataset.value
        });
    },

    // 提交估价
    async onSubmit() {
        const { vehicleFullName, brandSeries, years, mileage, grade, newPrice, city } = this.data;

        // 验证
        if (!vehicleFullName.trim()) {
            wx.showToast({ title: '请输入车辆全称', icon: 'none' });
            return;
        }
        if (!brandSeries.trim()) {
            wx.showToast({ title: '请输入品牌车系', icon: 'none' });
            return;
        }

        this.setData({ loading: true });

        try {
            const result = await app.request({
                url: '/predict',
                method: 'POST',
                data: {
                    vehicle_full_name: vehicleFullName,
                    brand_series: brandSeries,
                    years: parseFloat(years),
                    mileage: parseFloat(mileage) || 0,
                    grade: grade,
                    new_price: newPrice ? parseFloat(newPrice) : null,
                    city: city,
                    save_history: true
                }
            });

            if (result.success) {
                // 跳转到结果页
                wx.navigateTo({
                    url: `/pages/result/result?data=${encodeURIComponent(JSON.stringify(result))}&vehicle=${encodeURIComponent(vehicleFullName)}`
                });
            } else {
                wx.showToast({ title: result.detail || '估价失败', icon: 'none' });
            }
        } catch (e) {
            console.error('请求失败', e);
            wx.showToast({ title: '网络错误', icon: 'none' });
        } finally {
            this.setData({ loading: false });
        }
    },

    // 快速填充示例
    onFillExample() {
        this.setData({
            vehicleFullName: '丰田 凯美瑞 2015款 2.5G 豪华导航版',
            brandSeries: '丰田-凯美瑞',
            years: 10,
            mileage: '8.5',
            grade: '中',
            newPrice: '25',
            city: '北京'
        });
    },

    // 随机下一辆
    async onNextVehicle() {
        this.setData({ loading: true });
        try {
            const v = await app.request({ url: '/random_vehicle' });
            if (v.success) {
                // 评级映射
                let grade = v.grade;
                const gradeMap = { 'a': '优', 'b': '中', 'c': '差' };
                if (gradeMap[grade]) grade = gradeMap[grade];

                this.setData({
                    vehicleFullName: v.vehicle_full_name || v.model_name,
                    brandSeries: v.brand_series,
                    years: parseFloat(v.years || 5).toFixed(1),
                    mileage: parseFloat(v.mileage || 0).toFixed(1),
                    grade: grade || '中',
                    newPrice: v.new_price || '',
                    city: v.city || ''
                });
                // wx.showToast({ title: '已刷新', icon: 'none' });
            }
        } catch (e) {
            console.error(e);
            wx.showToast({ title: '获取失败', icon: 'none' });
        } finally {
            this.setData({ loading: false });
        }
    },

    // 跳转到历史记录
    goToHistory() {
        wx.navigateTo({
            url: '/pages/history/history'
        });
    },

    // 跳转到个人中心
    goToProfile() {
        wx.navigateTo({
            url: '/pages/profile/profile'
        });
    }
});
