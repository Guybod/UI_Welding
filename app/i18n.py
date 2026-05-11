from PySide6.QtCore import QObject, Signal

_STRINGS = {
    # 菜单栏
    "menu_connection":  {"zh": "连接",       "en": "Connection"},
    "menu_login":       {"zh": "登录",       "en": "Login"},
    "menu_return_login":{"zh": "返回登录页", "en": "Return to Login"},
    "menu_help":        {"zh": "帮助",       "en": "Help"},
    "menu_about":       {"zh": "关于",       "en": "About"},
    "menu_settings":    {"zh": "设置",       "en": "Settings"},
    "menu_language":    {"zh": "语言",       "en": "Language"},
    "menu_lang_zh":     {"zh": "中文",       "en": "Chinese"},
    "menu_lang_en":     {"zh": "English",    "en": "English"},
    "menu_style":       {"zh": "样式",       "en": "Style"},

    # 顶部标签
    "tab_home":     {"zh": "首页",   "en": "Home"},
    "tab_welding":  {"zh": "焊接",   "en": "Welding"},
    "tab_writing":  {"zh": "写字",   "en": "Writing"},
    "tab_motion":   {"zh": "运动",   "en": "Motion"},
    "tab_io":       {"zh": "IO",     "en": "IO"},
    "tab_program":  {"zh": "程序",   "en": "Program"},
    "tab_upload":   {"zh": "上传",   "en": "Upload"},
    "tab_settings": {"zh": "设置",   "en": "Settings"},

    # 状态栏
    "status_disconnected": {"zh": "未连接",     "en": "Disconnected"},
    "status_connected":    {"zh": "已连接",     "en": "Connected"},
    "status_reconnecting": {"zh": "重连中...",  "en": "Reconnecting..."},

    # 抽屉
    "drawer_motion":        {"zh": "运动",       "en": "Motion"},
    "drawer_joint_jog":     {"zh": "关节点动",   "en": "Joint Jog"},
    "drawer_cart_jog":      {"zh": "坐标系点动", "en": "Cartesian Jog"},
    "drawer_speed":         {"zh": "速度",       "en": "Speed"},
    "drawer_presets":       {"zh": "预设位",     "en": "Presets"},
    "drawer_home":          {"zh": "零点",       "en": "Home"},
    "drawer_safe":          {"zh": "安全点",     "en": "Safe"},
    "drawer_candle":        {"zh": "蜡烛位",     "en": "Candle"},
    "drawer_pack":          {"zh": "打包位",     "en": "Pack"},
    "drawer_pose_display":  {"zh": "位姿显示",   "en": "Pose Display"},
    "drawer_robot_model":   {"zh": "型号",       "en": "Model"},
    "drawer_coordinate":    {"zh": "坐标系",     "en": "Coordinate"},
    "drawer_tool":          {"zh": "工具",       "en": "Tool"},

    # 节点编辑器
    "node_library_title":   {"zh": "节点库",     "en": "Node Library"},
    "node_property_title":  {"zh": "属性",       "en": "Properties"},
    "node_log_title":       {"zh": "执行日志",   "en": "Execution Log"},
    "node_project_label":   {"zh": "工程:",      "en": "Project:"},
    "node_unnamed":         {"zh": "未命名",     "en": "Untitled"},
    "node_btn_save":        {"zh": "保存",       "en": "Save"},
    "node_btn_load":        {"zh": "加载",       "en": "Load"},
    "node_btn_validate":    {"zh": "校验",       "en": "Validate"},
    "node_btn_apply":       {"zh": "应用",       "en": "Apply"},
    "node_btn_update_pos":  {"zh": "更新为当前位置", "en": "Update Current Pose"},
    "node_saved":           {"zh": "已保存:",    "en": "Saved:"},
    "node_loaded":          {"zh": "已加载:",    "en": "Loaded:"},
    "node_save_failed":     {"zh": "保存失败",   "en": "Save Failed"},
    "node_load_failed":     {"zh": "加载失败",   "en": "Load Failed"},
    "node_valid_pass":      {"zh": "✅ 校验通过", "en": "✅ Validation passed"},
    "node_valid_fail":      {"zh": "❌ 校验失败", "en": "❌ Validation failed"},
    "node_select_hint":     {"zh": "请选择一个节点", "en": "Select a node"},
    "node_rename_title":    {"zh": "重命名节点",  "en": "Rename Node"},
    "node_rename_label":    {"zh": "名称:",       "en": "Name:"},
    "node_delete":          {"zh": "删除节点",    "en": "Delete Node"},
    "var_add":              {"zh": "添加变量",    "en": "Add Variable"},
    "var_delete":           {"zh": "删除变量",    "en": "Delete Variable"},
    "var_get":              {"zh": "获取变量",    "en": "Get Variable"},
    "var_set":              {"zh": "设置变量",    "en": "Set Variable"},
    "var_name":             {"zh": "名称:",       "en": "Name:"},
    "var_type":             {"zh": "类型:",       "en": "Type:"},
    "var_initial":          {"zh": "初始值:",     "en": "Initial:"},
    "var_edit":             {"zh": "编辑变量",    "en": "Edit Variable"},
    "pos_add":              {"zh": "添加点位",    "en": "Add Position"},
    "pos_delete":           {"zh": "删除点位",    "en": "Delete Position"},
    "port_split":           {"zh": "拆分",        "en": "Split"},
    "port_merge":           {"zh": "合并",        "en": "Merge"},
    "node_save_graph":      {"zh": "保存节点图",  "en": "Save Graph"},
    "node_load_graph":      {"zh": "加载节点图",  "en": "Load Graph"},

    # 节点库分类
    "cat_base":     {"zh": "基础",     "en": "Basic"},
    "cat_motion":   {"zh": "运动",     "en": "Motion"},
    "cat_position": {"zh": "点位",     "en": "Position"},
    "cat_math":     {"zh": "运算",     "en": "Math"},
    "cat_logic":    {"zh": "逻辑",     "en": "Logic"},
    "cat_string":   {"zh": "字符串",   "en": "String"},
    "cat_io":       {"zh": "IO",       "en": "IO"},
    "cat_register": {"zh": "寄存器",   "en": "Register"},
    "cat_variable": {"zh": "变量",     "en": "Variable"},
    "cat_constant": {"zh": "常量",     "en": "Constant"},
    "cat_custom":   {"zh": "自定义",   "en": "Custom"},

    # 节点名
    "node_Start":       {"zh": "开始",       "en": "Start"},
    "node_End":         {"zh": "结束",       "en": "End"},
    "node_Wait":        {"zh": "等待",       "en": "Wait"},
    "node_Print":       {"zh": "打印",       "en": "Print"},
    "node_MoveJ":       {"zh": "关节运动",   "en": "MoveJ"},
    "node_MoveL":       {"zh": "直线运动",   "en": "MoveL"},
    "node_MoveC":       {"zh": "圆弧运动",   "en": "MoveC"},
    "node_MoveCircle":  {"zh": "整圆运动",   "en": "MoveCircle"},
    "node_MovePath":    {"zh": "路径运动",   "en": "MovePath"},
    "node_Position":    {"zh": "点位",       "en": "Position"},
    "node_Add":         {"zh": "加",         "en": "Add"},
    "node_Sub":         {"zh": "减",         "en": "Sub"},
    "node_Mul":         {"zh": "乘",         "en": "Mul"},
    "node_Div":         {"zh": "除",         "en": "Div"},
    "node_Pow":         {"zh": "幂",         "en": "Pow"},
    "node_Mod":         {"zh": "取余",       "en": "Mod"},
    "node_Abs":         {"zh": "绝对值",     "en": "Abs"},
    "node_Neg":         {"zh": "取反",       "en": "Neg"},
    "node_Square":      {"zh": "平方",       "en": "Square"},
    "node_Sqrt":        {"zh": "开方",       "en": "Sqrt"},
    "node_Sin":         {"zh": "正弦",       "en": "Sin"},
    "node_Cos":         {"zh": "余弦",       "en": "Cos"},
    "node_Tan":         {"zh": "正切",       "en": "Tan"},
    "node_Deg2Rad":     {"zh": "度转弧度",   "en": "Deg2Rad"},
    "node_Rad2Deg":     {"zh": "弧度转度",   "en": "Rad2Deg"},
    "node_MatMulL":     {"zh": "矩阵左乘",   "en": "MatMulL"},
    "node_MatMulR":     {"zh": "矩阵右乘",   "en": "MatMulR"},
    "node_Int2Float":   {"zh": "整转浮",     "en": "Int2Float"},
    "node_BreakPosition": {"zh": "拆分点位",   "en": "BreakPosition"},
    "node_MakePosition": {"zh": "组合点位",   "en": "MakePosition"},
    "node_Float2Int":   {"zh": "浮转整",     "en": "Float2Int"},
    "node_And":         {"zh": "与",         "en": "And"},
    "node_Or":          {"zh": "或",         "en": "Or"},
    "node_Not":         {"zh": "非",         "en": "Not"},
    "node_Xor":         {"zh": "异或",       "en": "Xor"},
    "node_Gt":          {"zh": "大于",       "en": "Gt"},
    "node_Lt":          {"zh": "小于",       "en": "Lt"},
    "node_Eq":          {"zh": "等于",       "en": "Eq"},
    "node_Ge":          {"zh": "大于等于",   "en": "Ge"},
    "node_Le":          {"zh": "小于等于",   "en": "Le"},
    "node_If":          {"zh": "如果",       "en": "If"},
    "node_For":         {"zh": "循环",       "en": "For"},
    "node_While":       {"zh": "条件循环",   "en": "While"},
    "node_Compare":     {"zh": "比较",       "en": "Compare"},
    "node_StrConcat":   {"zh": "字符串拼接", "en": "StrConcat"},
    "node_StrSplit":    {"zh": "字符串分割", "en": "StrSplit"},
    "node_StrFind":     {"zh": "字符串查找", "en": "StrFind"},
    "node_StrReplace":  {"zh": "字符串替换", "en": "StrReplace"},
    "node_StrLen":      {"zh": "字符串长度", "en": "StrLen"},
    "node_Num2Str":     {"zh": "数值转串",   "en": "Num2Str"},
    "node_Bool2Str":    {"zh": "布尔转串",   "en": "Bool2Str"},
    "node_SetDO":       {"zh": "设置DO",     "en": "SetDO"},
    "node_ReadDI":      {"zh": "读取DI",     "en": "ReadDI"},
    "node_SetAO":       {"zh": "设置AO",     "en": "SetAO"},
    "node_ReadAI":      {"zh": "读取AI",     "en": "ReadAI"},
    "node_SetRegister": {"zh": "写寄存器",   "en": "SetRegister"},
    "node_ReadRegister":{"zh": "读寄存器",   "en": "ReadRegister"},
    "node_Int":         {"zh": "整数",       "en": "Int"},
    "node_Float":       {"zh": "浮点数",     "en": "Float"},
    "node_Bool":        {"zh": "布尔",       "en": "Bool"},
    "node_String":      {"zh": "字符串",     "en": "String"},
    "node_Array":       {"zh": "数组",       "en": "Array"},
    "node_ArrayGet":    {"zh": "取数组元素", "en": "ArrayGet"},
    "node_ArraySet":    {"zh": "设置数组元素","en": "ArraySet"},

    # 底部命令栏
    "cmd_enable":       {"zh": "使能",       "en": "Enable"},
    "cmd_disable":      {"zh": "下使能",     "en": "Disable"},
    "cmd_stop_move":    {"zh": "停止运动",   "en": "Stop Move"},
    "cmd_pause":        {"zh": "暂停",       "en": "Pause"},
    "cmd_resume":       {"zh": "恢复",       "en": "Resume"},
    "cmd_manual":       {"zh": "手动",       "en": "Manual"},
    "cmd_auto":         {"zh": "自动",       "en": "Auto"},
    "cmd_remote":       {"zh": "远程",       "en": "Remote"},
    "cmd_simulation":   {"zh": "仿真",       "en": "Sim"},
    "cmd_actual":       {"zh": "实机",       "en": "Real"},
    "cmd_project_start":{"zh": "启动工程",   "en": "Run"},
    "cmd_project_stop": {"zh": "停止工程",   "en": "Stop"},
    "cmd_project_pause":{"zh": "暂停工程",   "en": "Pause"},
    "cmd_project_resume":{"zh": "恢复工程",  "en": "Resume"},
    "cmd_error_title":  {"zh": "错误",       "en": "Error"},
    "cmd_clear_error":  {"zh": "清除错误",   "en": "Clear Error"},

    # Position 属性
    "pos_name":         {"zh": "名称:",       "en": "Name:"},
    "pos_jp_group":     {"zh": "关节角 jp (deg)",  "en": "Joint Angles jp (deg)"},
    "pos_cp_group":     {"zh": "笛卡尔位姿 cp (mm / deg)", "en": "Cartesian Pose cp (mm / deg)"},
    "pos_opt_group":    {"zh": "默认运动参数 optional", "en": "Default Motion Params (optional)"},
    "pos_speed":        {"zh": "速度:",       "en": "Speed:"},
    "pos_acc":          {"zh": "加速度:",     "en": "Acceleration:"},
    "pos_blend_abs":    {"zh": "过渡半径(绝对):", "en": "Blend Radius (abs):"},
    "pos_blend_rel":    {"zh": "过渡半径(相对):", "en": "Blend Radius (rel):"},

    # 校验
    "val_missing_start":    {"zh": "缺少 Start 节点",  "en": "Missing Start node"},
    "val_missing_end":      {"zh": "缺少 End 节点",    "en": "Missing End node"},
    "val_dup_id":           {"zh": "节点 ID 重复",     "en": "Duplicate node ID"},
    "val_edge_src_missing": {"zh": "源节点不存在",     "en": "Source node not found"},
    "val_edge_tgt_missing": {"zh": "目标节点不存在",   "en": "Target node not found"},
    "val_edge_port_missing":    {"zh": "端口不存在",        "en": "Port not found"},
    "val_edge_port_not_input":  {"zh": "不是输入端口",      "en": "Not an input port"},
    "val_edge_port_not_output": {"zh": "不是输出端口",      "en": "Not an output port"},
    "val_edge_type_mismatch":   {"zh": "端口类型不匹配",    "en": "Port type mismatch"},
    "val_flow_unreachable":     {"zh": "无法从 Start 通过 flow 连线到达", "en": "Unreachable from Start via flow"},
    "val_flow_input_unconnected":{"zh": "flow 输入端口未连接", "en": "Flow input not connected"},
    "val_pose_unconnected":     {"zh": "pose 输入未连接，必须连接 Position 节点", "en": "Pose input must connect to a Position node"},
    "val_pose_not_position":    {"zh": "连接的不是 Position 节点", "en": "Connected node is not a Position"},
}


class I18nManager(QObject):
    """中英文切换管理器"""
    language_changed = Signal(str)  # emits "zh" or "en"

    _instance = None

    def __init__(self):
        super().__init__()
        self._lang = "zh"

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def lang(self) -> str:
        return self._lang

    def set_lang(self, lang: str):
        if lang != self._lang:
            self._lang = lang
            self.language_changed.emit(lang)

    def tr(self, key: str) -> str:
        entry = _STRINGS.get(key, {})
        return entry.get(self._lang, key)


def tr(key: str) -> str:
    return I18nManager.instance().tr(key)


def tr_node(node_type: str) -> str:
    """翻译节点类型名"""
    key = f"node_{node_type}"
    return tr(key)

