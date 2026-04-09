// 全局配置
const config = {
    // API 地址
    // 开发工具模拟器（本地）用:
    // apiBaseUrl: 'http://127.0.0.1:8003/api',
    // 真机调试（手机与电脑在同一 WiFi 下）用局域网 IP:
    apiBaseUrl: 'http://192.168.1.53:8003/api',
    // 生产环境:
    // apiBaseUrl: 'https://your-domain.com/api',
};

App({
    config: config,
    globalData: {
        userInfo: null,
        token: null,
        config: config
    },

    getApiBaseUrl() {
        const overrideUrl = wx.getStorageSync('apiBaseUrl');
        if (overrideUrl) {
            return overrideUrl;
        }
        return this.config?.apiBaseUrl || this.globalData.config?.apiBaseUrl || '';
    },

    isDevEnvironment() {
        const apiBaseUrl = this.getApiBaseUrl();
        return apiBaseUrl.includes('127.0.0.1') || apiBaseUrl.includes('localhost');
    },

    loginWithEnvironment() {
        return this.isDevEnvironment() ? this.testLogin() : this.login();
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
                            url: `${this.getApiBaseUrl()}/auth/login`,
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

    // 测试登录 (开发环境) - 使用固定的 openid 避免每次创建新用户
    testLogin() {
        // 复用 Storage 中已存在的 test_openid，避免每次生成新用户占满 Supabase
        let stableOpenid = wx.getStorageSync('dev_test_openid');
        if (!stableOpenid) {
            stableOpenid = 'test_dev_' + Math.random().toString(36).slice(2, 10);
            wx.setStorageSync('dev_test_openid', stableOpenid);
        }
        return new Promise((resolve, reject) => {
            wx.request({
                url: `${this.getApiBaseUrl()}/auth/test-login`,
                method: 'POST',
                data: {
                    test_openid: stableOpenid,
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
                url: options.url.startsWith('http') ? options.url : `${this.getApiBaseUrl()}${options.url}`,
                header: {
                    'Content-Type': 'application/json',
                    'Authorization': token ? `Bearer ${token}` : '',
                    ...options.header
                },
                success: (response) => {
                    if (response.statusCode === 401) {
                        // Token 过期或无效，尝试重新登录
                        this.loginWithEnvironment().then(() => {
                            // 登录成功后重试原请求
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
