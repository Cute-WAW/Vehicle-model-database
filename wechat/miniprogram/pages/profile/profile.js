const app = getApp();

Page({
    data: {
        loggedIn: false,
        userInfo: null,
        isDev: false,
        tokenPreview: ''
    },

    onShow() {
        this.checkLoginStatus();
    },

    checkLoginStatus() {
        const token = app.globalData.token;
        const userInfo = app.globalData.userInfo;
        const isDev = app.isDevEnvironment();
        
        let tokenPreview = '';
        if (token) {
            tokenPreview = token.substring(0, 15) + '...' + token.substring(token.length - 15);
        }

        this.setData({
            loggedIn: !!token,
            userInfo: userInfo || null,
            isDev: isDev,
            tokenPreview: tokenPreview
        });
    },

    goToLogin() {
        wx.navigateTo({
            url: '/pages/login/login'
        });
    },

    handleLogout() {
        wx.showModal({
            title: '提示',
            content: '确定要退出登录吗？',
            success: (res) => {
                if (res.confirm) {
                    app.logout();
                    this.checkLoginStatus();
                    wx.showToast({ title: '已退出登录', icon: 'none' });
                }
            }
        });
    }
});
