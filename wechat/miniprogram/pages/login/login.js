const app = getApp();

Page({
    data: {
        loading: false
    },

    async handleLogin() {
        this.setData({ loading: true });
        try {
            await app.loginWithEnvironment();
            wx.showToast({ title: '登录成功', icon: 'success' });
            setTimeout(() => {
                wx.navigateBack({ delta: 1 });
            }, 1000);
        } catch (e) {
            console.error('登录异常', e);
            wx.showToast({ title: '登录失败，请重试', icon: 'none' });
        } finally {
            this.setData({ loading: false });
        }
    },

    handleCancel() {
        wx.navigateBack({ delta: 1 });
    }
});
