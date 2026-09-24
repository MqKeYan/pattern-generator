// 主界面任务通知：仅服务当前客户端的任务，配置按客户端号保存在本地浏览器。

const CLIENT_TASK_NOTIFICATION_STORAGE_PREFIX = 'client_task_notifications:';
const CLIENT_NOTIFICATION_CHANNEL_DEFINITIONS = {
    pushplus: { labelKey: 'task_notification_pushplus', required: ['token'], fields: [
        { key: 'token', labelKey: 'task_notification_token', type: 'password', secret: true },
    ] },
    webhook: { labelKey: 'task_notification_webhook', required: ['url'], fields: [{ key: 'url', labelKey: 'task_notification_webhook_url', type: 'url', secret: true }] },
    email: { labelKey: 'task_notification_email', required: ['host', 'recipient'], fields: [
        { key: 'host', labelKey: 'task_notification_email_host', type: 'text' },
        { key: 'port', labelKey: 'task_notification_email_port', type: 'number' },
        { key: 'ssl', labelKey: 'task_notification_email_ssl', type: 'checkbox' },
        { key: 'starttls', labelKey: 'task_notification_email_starttls', type: 'checkbox' },
        { key: 'username', labelKey: 'task_notification_email_username', type: 'text' },
        { key: 'password', labelKey: 'task_notification_email_password', type: 'password', secret: true },
        { key: 'sender', labelKey: 'task_notification_email_sender', type: 'email' },
        { key: 'recipient', labelKey: 'task_notification_email_recipient', type: 'email' },
    ] },
    telegram: { labelKey: 'task_notification_telegram', required: ['token', 'chat_id'], fields: [
        { key: 'token', labelKey: 'task_notification_telegram_token', type: 'password', secret: true },
        { key: 'chat_id', labelKey: 'task_notification_telegram_chat_id', type: 'text' },
    ] },
    discord: { labelKey: 'task_notification_discord', required: ['url'], fields: [{ key: 'url', labelKey: 'task_notification_discord_url', type: 'url', secret: true }] },
    dingtalk: { labelKey: 'task_notification_dingtalk', required: ['url'], fields: [
        { key: 'url', labelKey: 'task_notification_dingtalk_url', type: 'url', secret: true },
        { key: 'secret', labelKey: 'task_notification_dingtalk_secret', type: 'password', secret: true },
    ] },
    feishu: { labelKey: 'task_notification_feishu', required: ['url'], fields: [
        { key: 'url', labelKey: 'task_notification_feishu_url', type: 'url', secret: true },
        { key: 'secret', labelKey: 'task_notification_feishu_secret', type: 'password', secret: true },
    ] },
    wecom: { labelKey: 'task_notification_wecom', required: ['url'], fields: [{ key: 'url', labelKey: 'task_notification_wecom_url', type: 'url', secret: true }] },
};
const CLIENT_TASK_NOTIFICATION_DEFAULTS = {
    enabled: false,
    browser: true,
    sound: false,
    pushplus: false,
    pushplusToken: '',
    pushplusTargets: [],
    channelTargets: {},
    channels: {
        webhook: { enabled: false, url: '' },
        email: { enabled: false, host: '', port: 465, ssl: true, starttls: false, username: '', password: '', sender: '', recipient: '' },
        telegram: { enabled: false, token: '', chat_id: '' },
        discord: { enabled: false, url: '' },
        dingtalk: { enabled: false, url: '', secret: '' },
        feishu: { enabled: false, url: '', secret: '' },
        wecom: { enabled: false, url: '' },
    },
    events: { completed: true, failed: true, cancelled: false, timeout: true },
};

Object.assign(window.I18N_LOCALES['zh-CN'], {
    task_notification_title: '本客户端任务通知', task_notification_enable: '启用任务通知',
    task_notification_browser: 'Windows 系统通知', task_notification_sound: '提示音',
    task_notification_pushplus: 'PushPlus 推送', task_notification_completed: '任务完成',
    task_notification_failed: '任务失败', task_notification_cancelled: '任务取消',
    task_notification_timeout: '任务超时', task_notification_token: 'PushPlus Token',
    task_notification_test: '测试通知',
    task_notification_manage: '管理第三方推送', task_notification_settings_title: '第三方推送设置',
    task_notification_settings_desc: '仅保存本客户端的第三方推送绑定信息。', task_notification_restore: '恢复默认推送',
    task_notification_settings_saved: 'PushPlus 设置已保存', task_notification_settings_restored: 'PushPlus 已恢复默认',
    pushplus_targets_title: 'PushPlus 推送目标', pushplus_target_add: '新增目标', pushplus_target_new: '新增 PushPlus 目标',
    pushplus_target_name: '目标名称', pushplus_target_enabled: '启用此目标', pushplus_target_enabled_short: '启用', pushplus_target_disabled_short: '停用', pushplus_target_save: '保存目标',
    pushplus_target_edit: '编辑', pushplus_target_delete: '删除', pushplus_target_edit_title: '编辑 PushPlus 目标',
    pushplus_target_empty: '暂无 PushPlus 推送目标', pushplus_target_required: '请填写目标名称和 PushPlus Token', pushplus_target_limit: '最多可配置20个 PushPlus 目标',
    pushplus_target_status: '状态', pushplus_target_token: 'Token', pushplus_target_actions: '操作', pushplus_target_not_configured: '未配置',
    task_notification_target_type: '平台', task_notification_target_name: '目标名称', task_notification_target_status: '状态', task_notification_target_config: '配置', task_notification_target_configured: '已配置', task_notification_target_not_configured: '未配置', task_notification_target_actions: '操作', task_notification_target_add: '新增目标', task_notification_target_new: '新增第三方推送目标', task_notification_target_edit_title: '编辑第三方推送目标', task_notification_target_empty: '暂无第三方推送目标', task_notification_target_required: '请填写目标名称并完成平台配置', task_notification_target_save: '保存目标', task_notification_target_limit: '最多可配置20个第三方推送目标', task_notification_target_enabled: '启用', task_notification_target_disabled: '停用',
    task_notification_test_title: '任务通知测试', task_notification_test_body: '本客户端任务通知已启用。',
    task_notification_completed_title: '{model} 任务完成', task_notification_completed_body: '{model} 已完成计算。',
    task_notification_failed_title: '{model} 任务失败', task_notification_failed_body: '{model} 计算失败。',
    task_notification_cancelled_title: '{model} 任务已取消', task_notification_cancelled_body: '{model} 已取消。',
    task_notification_timeout_title: '{model} 任务超时', task_notification_timeout_body: '{model} 已超时。',
    task_notification_permission_denied: 'Windows 系统通知权限未授予，已改用窗口提示。',
    task_notification_unsupported: '当前浏览器不支持 Windows 系统通知，请启用 PushPlus 或更换浏览器。',
    task_notification_insecure: '当前访问地址不支持 Windows 系统通知，请使用 localhost 或 HTTPS。',
    task_notification_denied: 'Windows 系统通知已被浏览器或系统阻止，请在网站权限和 Windows 通知设置中允许。',
});
Object.assign(window.I18N_LOCALES['zh-TW'], {
    task_notification_title: '本用戶端任務通知', task_notification_enable: '啟用任務通知',
    task_notification_browser: 'Windows 系統通知', task_notification_sound: '提示音',
    task_notification_pushplus: 'PushPlus 推送', task_notification_completed: '任務完成',
    task_notification_failed: '任務失敗', task_notification_cancelled: '任務取消',
    task_notification_timeout: '任務逾時', task_notification_token: 'PushPlus Token',
    task_notification_test: '測試通知',
    task_notification_manage: '管理第三方推送', task_notification_settings_title: '第三方推送設定',
    task_notification_settings_desc: '僅保存本用戶端的第三方推送綁定資訊。', task_notification_restore: '恢復預設推送',
    task_notification_settings_saved: 'PushPlus 設定已保存', task_notification_settings_restored: 'PushPlus 已恢復預設',
    pushplus_targets_title: 'PushPlus 推送目標', pushplus_target_add: '新增目標', pushplus_target_new: '新增 PushPlus 目標',
    pushplus_target_name: '目標名稱', pushplus_target_enabled: '啟用此目標', pushplus_target_enabled_short: '啟用', pushplus_target_disabled_short: '停用', pushplus_target_save: '保存目標',
    pushplus_target_edit: '編輯', pushplus_target_delete: '刪除', pushplus_target_edit_title: '編輯 PushPlus 目標',
    pushplus_target_empty: '暫無 PushPlus 推送目標', pushplus_target_required: '請填寫目標名稱和 PushPlus Token', pushplus_target_limit: '最多可設定20個 PushPlus 推送目標',
    pushplus_target_status: '狀態', pushplus_target_token: 'Token', pushplus_target_actions: '操作', pushplus_target_not_configured: '未設定',
    task_notification_target_type: '平台', task_notification_target_name: '目標名稱', task_notification_target_status: '狀態', task_notification_target_config: '設定', task_notification_target_configured: '已設定', task_notification_target_not_configured: '未設定', task_notification_target_actions: '操作', task_notification_target_add: '新增目標', task_notification_target_new: '新增第三方推送目標', task_notification_target_edit_title: '編輯第三方推送目標', task_notification_target_empty: '暫無第三方推送目標', task_notification_target_required: '請填寫目標名稱並完成平台設定', task_notification_target_save: '保存目標', task_notification_target_limit: '最多可設定20個第三方推送目標', task_notification_target_enabled: '啟用', task_notification_target_disabled: '停用',
    task_notification_test_title: '任務通知測試', task_notification_test_body: '本用戶端任務通知已啟用。',
    task_notification_completed_title: '{model} 任務完成', task_notification_completed_body: '{model} 已完成計算。',
    task_notification_failed_title: '{model} 任務失敗', task_notification_failed_body: '{model} 計算失敗。',
    task_notification_cancelled_title: '{model} 任務已取消', task_notification_cancelled_body: '{model} 已取消。',
    task_notification_timeout_title: '{model} 任務逾時', task_notification_timeout_body: '{model} 已逾時。',
    task_notification_permission_denied: 'Windows 系統通知權限未授予，已改用視窗提示。',
    task_notification_unsupported: '目前瀏覽器不支援 Windows 系統通知，請啟用 PushPlus 或更換瀏覽器。',
    task_notification_insecure: '目前存取位址不支援 Windows 系統通知，請使用 localhost 或 HTTPS。',
    task_notification_denied: 'Windows 系統通知已被瀏覽器或系統封鎖，請在網站權限與 Windows 通知設定中允許。',
});
Object.assign(window.I18N_LOCALES.en, {
    task_notification_title: 'This Client Task Notifications', task_notification_enable: 'Enable Task Notifications',
    task_notification_browser: 'Windows System Notification', task_notification_sound: 'Notification Sound',
    task_notification_pushplus: 'PushPlus Notification', task_notification_completed: 'Task Completed',
    task_notification_failed: 'Task Failed', task_notification_cancelled: 'Task Cancelled',
    task_notification_timeout: 'Task Timed Out', task_notification_token: 'PushPlus Token',
    task_notification_test: 'Test Notification',
    task_notification_manage: 'Manage Third-Party Push', task_notification_settings_title: 'Third-Party Push Settings',
    task_notification_settings_desc: 'Only this client’s third-party push bindings are saved.', task_notification_restore: 'Restore Default Push',
    task_notification_settings_saved: 'PushPlus settings saved', task_notification_settings_restored: 'PushPlus restored',
    pushplus_targets_title: 'PushPlus Targets', pushplus_target_add: 'Add Target', pushplus_target_new: 'Add PushPlus Target',
    pushplus_target_name: 'Target Name', pushplus_target_enabled: 'Enable This Target', pushplus_target_enabled_short: 'Enabled', pushplus_target_disabled_short: 'Disabled', pushplus_target_save: 'Save Target',
    pushplus_target_edit: 'Edit', pushplus_target_delete: 'Delete', pushplus_target_edit_title: 'Edit PushPlus Target',
    pushplus_target_empty: 'No PushPlus targets', pushplus_target_required: 'Enter a target name and PushPlus Token', pushplus_target_limit: 'A maximum of 20 PushPlus targets can be configured',
    pushplus_target_status: 'Status', pushplus_target_token: 'Token', pushplus_target_actions: 'Actions', pushplus_target_not_configured: 'Not configured',
    task_notification_target_type: 'Platform', task_notification_target_name: 'Target Name', task_notification_target_status: 'Status', task_notification_target_config: 'Configuration', task_notification_target_configured: 'Configured', task_notification_target_not_configured: 'Not configured', task_notification_target_actions: 'Actions', task_notification_target_add: 'Add Target', task_notification_target_new: 'Add Third-Party Push Target', task_notification_target_edit_title: 'Edit Third-Party Push Target', task_notification_target_empty: 'No third-party push targets', task_notification_target_required: 'Enter a target name and complete the platform configuration', task_notification_target_save: 'Save Target', task_notification_target_limit: 'A maximum of 20 third-party push targets can be configured', task_notification_target_enabled: 'Enabled', task_notification_target_disabled: 'Disabled',
    task_notification_test_title: 'Task Notification Test', task_notification_test_body: 'This client task notification is enabled.',
    task_notification_completed_title: '{model} Task Completed', task_notification_completed_body: '{model} has completed.',
    task_notification_failed_title: '{model} Task Failed', task_notification_failed_body: '{model} has failed.',
    task_notification_cancelled_title: '{model} Task Cancelled', task_notification_cancelled_body: '{model} was cancelled.',
    task_notification_timeout_title: '{model} Task Timed Out', task_notification_timeout_body: '{model} timed out.',
    task_notification_permission_denied: 'Windows notification permission was not granted. A window toast is used instead.',
    task_notification_unsupported: 'This browser does not support Windows system notifications. Enable PushPlus or use another browser.',
    task_notification_insecure: 'This address does not support Windows system notifications. Use localhost or HTTPS.',
    task_notification_denied: 'Windows system notifications are blocked by the browser or system. Allow them in site and Windows notification settings.',
});
Object.assign(window.I18N_LOCALES.ja, {
    task_notification_title: 'このクライアントのタスク通知', task_notification_enable: 'タスク通知を有効化',
    task_notification_browser: 'Windows システム通知', task_notification_sound: '通知音',
    task_notification_pushplus: 'PushPlus 通知', task_notification_completed: 'タスク完了',
    task_notification_failed: 'タスク失敗', task_notification_cancelled: 'タスク取消',
    task_notification_timeout: 'タスクタイムアウト', task_notification_token: 'PushPlus Token',
    task_notification_test: '通知をテスト',
    task_notification_manage: '第三者通知を管理', task_notification_settings_title: '第三者通知設定',
    task_notification_settings_desc: 'このクライアントの第三者通知設定のみ保存します。', task_notification_restore: '通知設定を初期化',
    task_notification_settings_saved: 'PushPlus設定を保存しました', task_notification_settings_restored: 'PushPlusを初期化しました',
    pushplus_targets_title: 'PushPlus送信先', pushplus_target_add: '送信先を追加', pushplus_target_new: 'PushPlus送信先を追加',
    pushplus_target_name: '送信先名', pushplus_target_enabled: 'この送信先を有効化', pushplus_target_enabled_short: '有効', pushplus_target_disabled_short: '停止', pushplus_target_save: '送信先を保存',
    pushplus_target_edit: '編集', pushplus_target_delete: '削除', pushplus_target_edit_title: 'PushPlus送信先を編集',
    pushplus_target_empty: 'PushPlus送信先はありません', pushplus_target_required: '送信先名とPushPlus Tokenを入力してください', pushplus_target_limit: 'PushPlus送信先は最大20件まで設定できます',
    pushplus_target_status: '状態', pushplus_target_token: 'Token', pushplus_target_actions: '操作', pushplus_target_not_configured: '未設定',
    task_notification_target_type: 'プラットフォーム', task_notification_target_name: '送信先名', task_notification_target_status: '状態', task_notification_target_config: '設定', task_notification_target_configured: '設定済み', task_notification_target_not_configured: '未設定', task_notification_target_actions: '操作', task_notification_target_add: '送信先を追加', task_notification_target_new: '第三者通知送信先を追加', task_notification_target_edit_title: '第三者通知送信先を編集', task_notification_target_empty: '第三者通知送信先はありません', task_notification_target_required: '送信先名とプラットフォーム設定を入力してください', task_notification_target_save: '送信先を保存', task_notification_target_limit: '第三者通知送信先は最大20件まで設定できます', task_notification_target_enabled: '有効', task_notification_target_disabled: '停止',
    task_notification_test_title: 'タスク通知テスト', task_notification_test_body: 'このクライアントのタスク通知は有効です。',
    task_notification_completed_title: '{model} タスク完了', task_notification_completed_body: '{model} の計算が完了しました。',
    task_notification_failed_title: '{model} タスク失敗', task_notification_failed_body: '{model} の計算に失敗しました。',
    task_notification_cancelled_title: '{model} タスク取消', task_notification_cancelled_body: '{model} は取り消されました。',
    task_notification_timeout_title: '{model} タスクタイムアウト', task_notification_timeout_body: '{model} はタイムアウトしました。',
    task_notification_permission_denied: 'Windows 通知の権限がありません。画面内通知に切り替えました。',
    task_notification_unsupported: 'このブラウザは Windows システム通知に対応していません。PushPlus または別のブラウザを使用してください。',
    task_notification_insecure: 'このアドレスは Windows システム通知に対応していません。localhost または HTTPS を使用してください。',
    task_notification_denied: 'Windows システム通知がブラウザまたはシステムでブロックされています。サイトと Windows の通知設定で許可してください。',
});
Object.assign(window.I18N_LOCALES.ko, {
    task_notification_title: '이 클라이언트 작업 알림', task_notification_enable: '작업 알림 사용',
    task_notification_browser: 'Windows 시스템 알림', task_notification_sound: '알림 소리',
    task_notification_pushplus: 'PushPlus 알림', task_notification_completed: '작업 완료',
    task_notification_failed: '작업 실패', task_notification_cancelled: '작업 취소',
    task_notification_timeout: '작업 시간 초과', task_notification_token: 'PushPlus Token',
    task_notification_test: '알림 테스트',
    task_notification_manage: '타사 알림 관리', task_notification_settings_title: '타사 알림 설정',
    task_notification_settings_desc: '이 클라이언트의 타사 알림 설정만 저장합니다.', task_notification_restore: '알림 기본값 복원',
    task_notification_settings_saved: 'PushPlus 설정을 저장했습니다', task_notification_settings_restored: 'PushPlus를 기본값으로 복원했습니다',
    pushplus_targets_title: 'PushPlus 대상', pushplus_target_add: '대상 추가', pushplus_target_new: 'PushPlus 대상 추가',
    pushplus_target_name: '대상 이름', pushplus_target_enabled: '이 대상 사용', pushplus_target_enabled_short: '사용', pushplus_target_disabled_short: '중지', pushplus_target_save: '대상 저장',
    pushplus_target_edit: '편집', pushplus_target_delete: '삭제', pushplus_target_edit_title: 'PushPlus 대상 편집',
    pushplus_target_empty: 'PushPlus 대상이 없습니다', pushplus_target_required: '대상 이름과 PushPlus Token을 입력하세요', pushplus_target_limit: 'PushPlus 대상은 최대 20개까지 설정할 수 있습니다',
    pushplus_target_status: '상태', pushplus_target_token: 'Token', pushplus_target_actions: '작업', pushplus_target_not_configured: '미설정',
    task_notification_target_type: '플랫폼', task_notification_target_name: '대상 이름', task_notification_target_status: '상태', task_notification_target_config: '설정', task_notification_target_configured: '설정됨', task_notification_target_not_configured: '미설정', task_notification_target_actions: '작업', task_notification_target_add: '대상 추가', task_notification_target_new: '타사 알림 대상 추가', task_notification_target_edit_title: '타사 알림 대상 편집', task_notification_target_empty: '타사 알림 대상이 없습니다', task_notification_target_required: '대상 이름과 플랫폼 설정을 입력하세요', task_notification_target_save: '대상 저장', task_notification_target_limit: '타사 알림 대상은 최대 20개까지 설정할 수 있습니다', task_notification_target_enabled: '사용', task_notification_target_disabled: '중지',
    task_notification_test_title: '작업 알림 테스트', task_notification_test_body: '이 클라이언트의 작업 알림이 활성화되었습니다.',
    task_notification_completed_title: '{model} 작업 완료', task_notification_completed_body: '{model} 계산이 완료되었습니다.',
    task_notification_failed_title: '{model} 작업 실패', task_notification_failed_body: '{model} 계산에 실패했습니다.',
    task_notification_cancelled_title: '{model} 작업 취소', task_notification_cancelled_body: '{model} 작업이 취소되었습니다.',
    task_notification_timeout_title: '{model} 작업 시간 초과', task_notification_timeout_body: '{model} 작업 시간이 초과되었습니다.',
    task_notification_permission_denied: 'Windows 알림 권한이 없어 창 알림으로 전환했습니다.',
    task_notification_unsupported: '현재 브라우저는 Windows 시스템 알림을 지원하지 않습니다. PushPlus 또는 다른 브라우저를 사용하세요.',
    task_notification_insecure: '현재 주소는 Windows 시스템 알림을 지원하지 않습니다. localhost 또는 HTTPS를 사용하세요.',
    task_notification_denied: 'Windows 시스템 알림이 브라우저 또는 시스템에서 차단되었습니다. 사이트와 Windows 알림 설정에서 허용하세요.',
});

const EXTRA_CHANNEL_I18N = {
    'zh-CN': {
        task_notification_channels_title: '扩展通知渠道', task_notification_webhook: '通用 Webhook', task_notification_email: 'SMTP 邮件',
        task_notification_telegram: 'Telegram', task_notification_discord: 'Discord', task_notification_dingtalk: '钉钉机器人',
        task_notification_feishu: '飞书机器人', task_notification_wecom: '企业微信机器人', task_notification_webhook_url: 'Webhook 地址',
        task_notification_email_host: 'SMTP 服务器', task_notification_email_port: 'SMTP 端口', task_notification_email_ssl: 'SSL 加密',
        task_notification_email_starttls: 'STARTTLS', task_notification_email_username: 'SMTP 用户名', task_notification_email_password: 'SMTP 密码',
        task_notification_email_sender: '发件地址', task_notification_email_recipient: '收件地址', task_notification_telegram_token: 'Bot Token',
        task_notification_telegram_chat_id: 'Chat ID', task_notification_discord_url: 'Webhook 地址', task_notification_dingtalk_url: 'Webhook 地址',
        task_notification_dingtalk_secret: '签名密钥（可选）', task_notification_feishu_url: 'Webhook 地址', task_notification_feishu_secret: '签名密钥（可选）',
        task_notification_wecom_url: 'Webhook 地址',
    },
    'zh-TW': {
        task_notification_channels_title: '擴充通知渠道', task_notification_webhook: '通用 Webhook', task_notification_email: 'SMTP 郵件',
        task_notification_telegram: 'Telegram', task_notification_discord: 'Discord', task_notification_dingtalk: '釘釘機器人',
        task_notification_feishu: '飛書機器人', task_notification_wecom: '企業微信機器人', task_notification_webhook_url: 'Webhook 位址',
        task_notification_email_host: 'SMTP 伺服器', task_notification_email_port: 'SMTP 連接埠', task_notification_email_ssl: 'SSL 加密',
        task_notification_email_starttls: 'STARTTLS', task_notification_email_username: 'SMTP 使用者名稱', task_notification_email_password: 'SMTP 密碼',
        task_notification_email_sender: '寄件地址', task_notification_email_recipient: '收件地址', task_notification_telegram_token: 'Bot Token',
        task_notification_telegram_chat_id: 'Chat ID', task_notification_discord_url: 'Webhook 位址', task_notification_dingtalk_url: 'Webhook 位址',
        task_notification_dingtalk_secret: '簽名密鑰（可選）', task_notification_feishu_url: 'Webhook 位址', task_notification_feishu_secret: '簽名密鑰（可選）',
        task_notification_wecom_url: 'Webhook 位址',
    },
    en: {
        task_notification_channels_title: 'Additional Notification Channels', task_notification_webhook: 'Generic Webhook', task_notification_email: 'SMTP Email',
        task_notification_telegram: 'Telegram', task_notification_discord: 'Discord', task_notification_dingtalk: 'DingTalk Bot',
        task_notification_feishu: 'Feishu Bot', task_notification_wecom: 'WeCom Bot', task_notification_webhook_url: 'Webhook URL',
        task_notification_email_host: 'SMTP Server', task_notification_email_port: 'SMTP Port', task_notification_email_ssl: 'SSL Encryption',
        task_notification_email_starttls: 'STARTTLS', task_notification_email_username: 'SMTP Username', task_notification_email_password: 'SMTP Password',
        task_notification_email_sender: 'Sender Address', task_notification_email_recipient: 'Recipient Address', task_notification_telegram_token: 'Bot Token',
        task_notification_telegram_chat_id: 'Chat ID', task_notification_discord_url: 'Webhook URL', task_notification_dingtalk_url: 'Webhook URL',
        task_notification_dingtalk_secret: 'Signing Secret (Optional)', task_notification_feishu_url: 'Webhook URL', task_notification_feishu_secret: 'Signing Secret (Optional)',
        task_notification_wecom_url: 'Webhook URL',
    },
    ja: {
        task_notification_channels_title: '追加通知チャネル', task_notification_webhook: '汎用 Webhook', task_notification_email: 'SMTP メール',
        task_notification_telegram: 'Telegram', task_notification_discord: 'Discord', task_notification_dingtalk: 'DingTalk ボット',
        task_notification_feishu: 'Feishu ボット', task_notification_wecom: '企業微信ボット', task_notification_webhook_url: 'Webhook URL',
        task_notification_email_host: 'SMTP サーバー', task_notification_email_port: 'SMTP ポート', task_notification_email_ssl: 'SSL 暗号化',
        task_notification_email_starttls: 'STARTTLS', task_notification_email_username: 'SMTP ユーザー名', task_notification_email_password: 'SMTP パスワード',
        task_notification_email_sender: '送信者アドレス', task_notification_email_recipient: '受信者アドレス', task_notification_telegram_token: 'Bot Token',
        task_notification_telegram_chat_id: 'Chat ID', task_notification_discord_url: 'Webhook URL', task_notification_dingtalk_url: 'Webhook URL',
        task_notification_dingtalk_secret: '署名シークレット（任意）', task_notification_feishu_url: 'Webhook URL', task_notification_feishu_secret: '署名シークレット（任意）',
        task_notification_wecom_url: 'Webhook URL',
    },
    ko: {
        task_notification_channels_title: '추가 알림 채널', task_notification_webhook: '범용 Webhook', task_notification_email: 'SMTP 이메일',
        task_notification_telegram: 'Telegram', task_notification_discord: 'Discord', task_notification_dingtalk: 'DingTalk 봇',
        task_notification_feishu: 'Feishu 봇', task_notification_wecom: 'WeCom 봇', task_notification_webhook_url: 'Webhook 주소',
        task_notification_email_host: 'SMTP 서버', task_notification_email_port: 'SMTP 포트', task_notification_email_ssl: 'SSL 암호화',
        task_notification_email_starttls: 'STARTTLS', task_notification_email_username: 'SMTP 사용자 이름', task_notification_email_password: 'SMTP 비밀번호',
        task_notification_email_sender: '발신 주소', task_notification_email_recipient: '수신 주소', task_notification_telegram_token: 'Bot Token',
        task_notification_telegram_chat_id: 'Chat ID', task_notification_discord_url: 'Webhook 주소', task_notification_dingtalk_url: 'Webhook 주소',
        task_notification_dingtalk_secret: '서명 시크릿(선택)', task_notification_feishu_url: 'Webhook 주소', task_notification_feishu_secret: '서명 시크릿(선택)',
        task_notification_wecom_url: 'Webhook 주소',
    },
};
Object.entries(EXTRA_CHANNEL_I18N).forEach(([language, messages]) => Object.assign(window.I18N_LOCALES[language], messages));

function clientTaskNotificationStorageKey() {
    return `${CLIENT_TASK_NOTIFICATION_STORAGE_PREFIX}${state.clientId || 'pending'}`;
}

function getClientTaskNotificationSettings() {
    try {
        const saved = JSON.parse(localStorage.getItem(clientTaskNotificationStorageKey()) || '{}');
        const pushplusTargets = normalizeClientPushplusTargets(saved);
        return {
            ...CLIENT_TASK_NOTIFICATION_DEFAULTS,
            ...saved,
            pushplusTargets,
            channelTargets: normalizeClientChannelTargets(saved),
            events: { ...CLIENT_TASK_NOTIFICATION_DEFAULTS.events, ...(saved.events || {}) },
        };
    } catch {
        return { ...CLIENT_TASK_NOTIFICATION_DEFAULTS, events: { ...CLIENT_TASK_NOTIFICATION_DEFAULTS.events } };
    }
}

function normalizeClientPushplusTargets(settings = {}) {
    if (Array.isArray(settings.pushplusTargets)) {
        return settings.pushplusTargets
            .filter(target => target && typeof target === 'object' && typeof target.id === 'string')
            .slice(0, 20)
            .map((target, index) => ({
                id: target.id,
                name: String(target.name || `PushPlus ${index + 1}`).slice(0, 40),
                token: String(target.token || '').slice(0, 256),
                enabled: !!target.enabled,
            }));
    }
    if (!settings.pushplusToken) return [];
    return [{
        id: 'legacy-default',
        name: '默认 PushPlus',
        token: String(settings.pushplusToken).slice(0, 256),
        enabled: !!settings.pushplus,
    }];
}

function normalizeClientChannelTargets(settings = {}) {
    const raw = { ...(settings.channelTargets || settings.channels || {}) };
    if (!raw.pushplus && Array.isArray(settings.pushplusTargets)) raw.pushplus = settings.pushplusTargets;
    const result = {};
    Object.entries(CLIENT_NOTIFICATION_CHANNEL_DEFINITIONS).forEach(([type, definition]) => {
        const source = Array.isArray(raw[type]) ? raw[type] : (raw[type] && typeof raw[type] === 'object' ? [raw[type]] : []);
        const legacyConfigured = source.length === 1 && !Array.isArray(raw[type])
            && definition.fields.some(field => field.type !== 'checkbox' && String(source[0][field.key] || '').trim());
        result[type] = source
            .filter(target => target && typeof target === 'object')
            .filter((target, index) => Array.isArray(raw[type]) || legacyConfigured || !!target.enabled)
            .slice(0, 20)
            .map((target, index) => {
                const item = {
                    id: String(target.id || `legacy-${type}-${index + 1}`),
                    name: String(target.name || `默认${type}`).slice(0, 40),
                    enabled: !!target.enabled,
                };
                definition.fields.forEach(field => {
                    item[field.key] = field.type === 'checkbox' ? !!target[field.key] : String(target[field.key] || '').slice(0, 1024);
                });
                return item;
            });
    });
    return result;
}

function saveClientTaskNotificationSettings(settings) {
    localStorage.setItem(clientTaskNotificationStorageKey(), JSON.stringify(settings));
}

function readClientNotificationChannels() {
    return {
        webhook: { enabled: $('#tn-webhook').checked, url: $('#tn-webhook-url').value.trim() },
        email: {
            enabled: $('#tn-email').checked, host: $('#tn-email-host').value.trim(),
            port: parseInt($('#tn-email-port').value) || 465, ssl: $('#tn-email-ssl').checked,
            starttls: $('#tn-email-starttls').checked, username: $('#tn-email-username').value.trim(),
            password: $('#tn-email-password').value, sender: $('#tn-email-sender').value.trim(),
            recipient: $('#tn-email-recipient').value.trim(),
        },
        telegram: { enabled: $('#tn-telegram').checked, token: $('#tn-telegram-token').value.trim(), chat_id: $('#tn-telegram-chat-id').value.trim() },
        discord: { enabled: $('#tn-discord').checked, url: $('#tn-discord-url').value.trim() },
        dingtalk: { enabled: $('#tn-dingtalk').checked, url: $('#tn-dingtalk-url').value.trim(), secret: $('#tn-dingtalk-secret').value.trim() },
        feishu: { enabled: $('#tn-feishu').checked, url: $('#tn-feishu-url').value.trim(), secret: $('#tn-feishu-secret').value.trim() },
        wecom: { enabled: $('#tn-wecom').checked, url: $('#tn-wecom-url').value.trim() },
    };
}

function fillClientNotificationChannels(channels = {}) {
    const merged = { ...CLIENT_TASK_NOTIFICATION_DEFAULTS.channels, ...channels };
    $('#tn-webhook').checked = !!merged.webhook?.enabled;
    $('#tn-webhook-url').value = merged.webhook?.url || '';
    $('#tn-email').checked = !!merged.email?.enabled;
    $('#tn-email-host').value = merged.email?.host || '';
    $('#tn-email-port').value = merged.email?.port || 465;
    $('#tn-email-ssl').checked = merged.email?.ssl !== false;
    $('#tn-email-starttls').checked = !!merged.email?.starttls;
    $('#tn-email-username').value = merged.email?.username || '';
    $('#tn-email-password').value = merged.email?.password || '';
    $('#tn-email-sender').value = merged.email?.sender || '';
    $('#tn-email-recipient').value = merged.email?.recipient || '';
    $('#tn-telegram').checked = !!merged.telegram?.enabled;
    $('#tn-telegram-token').value = merged.telegram?.token || '';
    $('#tn-telegram-chat-id').value = merged.telegram?.chat_id || '';
    $('#tn-discord').checked = !!merged.discord?.enabled;
    $('#tn-discord-url').value = merged.discord?.url || '';
    $('#tn-dingtalk').checked = !!merged.dingtalk?.enabled;
    $('#tn-dingtalk-url').value = merged.dingtalk?.url || '';
    $('#tn-dingtalk-secret').value = merged.dingtalk?.secret || '';
    $('#tn-feishu').checked = !!merged.feishu?.enabled;
    $('#tn-feishu-url').value = merged.feishu?.url || '';
    $('#tn-feishu-secret').value = merged.feishu?.secret || '';
    $('#tn-wecom').checked = !!merged.wecom?.enabled;
    $('#tn-wecom-url').value = merged.wecom?.url || '';
}

function readClientTaskNotificationPreferences() {
    return {
        enabled: $('#tn-enabled').checked,
        browser: $('#tn-browser').checked,
        sound: $('#tn-sound').checked,
        events: {
            completed: $('#tn-completed').checked,
            failed: $('#tn-failed').checked,
            cancelled: $('#tn-cancelled').checked,
            timeout: $('#tn-timeout').checked,
        },
    };
}

function readClientTaskNotificationForm() {
    return {
        ...readClientTaskNotificationPreferences(),
        pushplusTargets: normalizeClientPushplusTargets(getClientTaskNotificationSettings()),
        channelTargets: normalizeClientChannelTargets(getClientTaskNotificationSettings()),
    };
}

function fillClientTaskNotificationPreferences(settings = getClientTaskNotificationSettings()) {
    $('#tn-enabled').checked = !!settings.enabled;
    $('#tn-browser').checked = !!settings.browser;
    $('#tn-sound').checked = !!settings.sound;
    Object.entries(settings.events).forEach(([event, enabled]) => {
        const input = $(`#tn-${event}`);
        if (input) input.checked = !!enabled;
    });
}

function fillClientTaskNotificationChannels(settings = getClientTaskNotificationSettings()) {
    // 第三方渠道改由独立管理弹窗维护，主设置页不再直接渲染渠道字段。
}

function fillClientTaskNotificationForm(settings = getClientTaskNotificationSettings()) {
    fillClientTaskNotificationPreferences(settings);
    fillClientTaskNotificationChannels(settings);
}

async function requestClientTaskNotificationPermission() {
    if (!window.isSecureContext || !('Notification' in window)) return false;
    if (Notification.permission === 'granted') return true;
    if (Notification.permission === 'denied') return false;
    try {
        return (await Notification.requestPermission()) === 'granted';
    } catch {
        return false;
    }
}

function clientTaskNotificationAvailability() {
    if (!('Notification' in window)) return 'unsupported';
    if (!window.isSecureContext) return 'insecure';
    return Notification.permission;
}

function playClientTaskNotificationSound() {
    try {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextClass) return;
        const context = new AudioContextClass();
        const oscillator = context.createOscillator();
        const gain = context.createGain();
        oscillator.frequency.value = 880;
        gain.gain.setValueAtTime(0.06, context.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + 0.22);
        oscillator.connect(gain).connect(context.destination);
        oscillator.start();
        oscillator.stop(context.currentTime + 0.22);
    } catch { /* 浏览器禁止声音时静默降级。 */ }
}

function currentTaskModelLabel(task) {
    const model = task?.model || state.currentModel || '模型1';
    const key = `model_${String(model).replace('模型', '')}`;
    return i18n.t(key) === key ? model : i18n.t(key);
}

function sendClientTaskBrowserNotification(title, body, type = 'info') {
    if ('Notification' in window && Notification.permission === 'granted') {
        new Notification(title, { body, icon: '/static/favicon.ico', tag: `pattern-task-${type}` });
        return true;
    }
    showToast(`${title}：${body}`, type === 'failed' || type === 'timeout' ? 'error' : 'success');
    return false;
}

function notifyCurrentClientTask(event, task) {
    const settings = getClientTaskNotificationSettings();
    if (!settings.enabled || !settings.events[event]) return;
    const model = currentTaskModelLabel(task);
    const title = i18n.t(`task_notification_${event}_title`, { model });
    const body = i18n.t(`task_notification_${event}_body`, { model });
    if (settings.browser) sendClientTaskBrowserNotification(title, body, event);
    if (settings.sound) playClientTaskNotificationSound();
}

async function testClientTaskNotification() {
    const settings = readClientTaskNotificationForm();
    if (settings.browser) {
        const availability = clientTaskNotificationAvailability();
        if (availability === 'unsupported') {
            showToast(i18n.t('task_notification_unsupported'), 'info');
            return;
        }
        if (availability === 'insecure') {
            showToast(i18n.t('task_notification_insecure'), 'info');
            return;
        }
        if (!(await requestClientTaskNotificationPermission())) {
            showToast(i18n.t('task_notification_denied'), 'info');
            return;
        }
        sendClientTaskBrowserNotification(
            i18n.t('task_notification_test_title'),
            i18n.t('task_notification_test_body'),
        );
    }
    if (settings.sound) playClientTaskNotificationSound();
    if (Object.values(settings.channelTargets || {}).some(targets => targets.some(target => target.enabled))) {
        try {
            const payload = clientTaskNotificationPayload({ ...settings, enabled: true });
            payload.client_id = state.clientId;
            const response = await fetch('/api/client-notifications/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                body: JSON.stringify(payload),
            });
            if (!response.ok) throw new Error('通知测试失败');
            showToast('扩展通知渠道测试已发送', 'success');
        } catch {
            showToast('扩展通知渠道测试失败', 'error');
        }
    }
}

function clientTaskNotificationPayload(settings = getClientTaskNotificationSettings()) {
    const pushplusTargets = normalizeClientPushplusTargets(settings)
        .filter(target => target.enabled && target.token);
    return {
        pushplus_targets: settings.enabled ? pushplusTargets : [],
        events: Object.entries(settings.events).filter(([, enabled]) => enabled).map(([event]) => event),
        channel_targets: settings.enabled ? normalizeClientChannelTargets(settings) : {},
        lang: i18n.getLang(),
        client_name: state.clientName || '',
    };
}
