// 全局配置
const config = {
    // API 地址 (开发环境用本地，生产环境改为云服务器地址)
    // apiBaseUrl: 'http://localhost:8003/api',
    // 真机调试请使用本机局域网IP
    apiBaseUrl: 'http://192.168.50.74:8003/api',
    // apiBaseUrl: 'https://your-domain.com/api',
};

App({
    globalData: {
        userInfo: null,
        token: null,
        config: config
    },

    onLaunch() {
        // 检查登录状态
        const token = wx.getStorageSync('token');
        if (token) {
            this.globalData.token = token;
            this.globalData.userInfo = wx.getStorageSync('userInfo');
        }
    },

    // 登录
    login() {
        return new Promise((resolve, reject) => {
            wx.login({
                success: (res) => {
                    if (res.code) {
                        // 发送 code 到后端换取 token
                        wx.request({
                            url: `${config.apiBaseUrl}/auth/login`,
                            method: 'POST',
                            data: {
                                code: res.code,
                                nickname: this.globalData.userInfo?.nickName || '用户',
                                avatar_url: this.globalData.userInfo?.avatarUrl || ''
                            },
                            success: (response) => {
                                if (response.data.success) {
                                    this.globalData.token = response.data.token;
                                    wx.setStorageSync('token', response.data.token);
                                    wx.setStorageSync('userInfo', response.data.user);
                                    resolve(response.data);
                                } else {
                                    reject(new Error('登录失败'));
                                }
                            },
                            fail: reject
                        });
                    } else {
                        reject(new Error('获取登录码失败'));
                    }
                },
                fail: reject
            });
        });
    },

    // 测试登录 (开发环境)
    testLogin() {
        return new Promise((resolve, reject) => {
            wx.request({
                url: `${config.apiBaseUrl}/auth/test-login`,
                method: 'POST',
                data: {
                    test_openid: 'test_' + Date.now(),
                    nickname: '测试用户'
                },
                success: (response) => {
                    if (response.data.success) {
                        this.globalData.token = response.data.token;
                        this.globalData.userInfo = response.data.user;
                        wx.setStorageSync('token', response.data.token);
                        wx.setStorageSync('userInfo', response.data.user);
                        resolve(response.data);
                    } else {
                        reject(new Error('测试登录失败'));
                    }
                },
                fail: reject
            });
        });
    },

    // 发送请求 (带 token)
    request(options) {
        const token = this.globalData.token;

        return new Promise((resolve, reject) => {
            wx.request({
                ...options,
                url: options.url.startsWith('http') ? options.url : `${config.apiBaseUrl}${options.url}`,
                header: {
                    'Content-Type': 'application/json',
                    'Authorization': token ? `Bearer ${token}` : '',
                    ...options.header
                },
                success: (response) => {
                    if (response.statusCode === 401) {
                        // Token 过期，重新登录
                        this.login().then(() => {
                            this.request(options).then(resolve).catch(reject);
                        }).catch(reject);
                    } else {
                        resolve(response.data);
                    }
                },
                fail: reject
            });
        });
    },

    // 退出登录
    logout() {
        this.globalData.token = null;
        this.globalData.userInfo = null;
        wx.removeStorageSync('token');
        wx.removeStorageSync('userInfo');
    }
});
