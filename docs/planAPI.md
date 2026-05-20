## 1. 通信基础

### 1.1 通信协议

- **协议**: TCP/IP、UDP

- **服务端**: 机器人控制器

- **端口号**: 9001（主接口）,
  9002（远程脚本模式），9030（UDP协议CRI实时控制接口）

- **默认IP**: 192.168.1.136

- **数据格式**: JSON字符串，UTF-8编码

### **1.2使用说明**

1.  **连接建立**: 使用TCP连接到机器人控制器IP:9001端口

2.  **请求格式**: 所有请求必须遵循标准JSON格式

3.  **错误处理**: 检查响应中的err字段处理错误

4.  **心跳维护**: 点动和RunTo运动需要定期发送心跳维持

5.  **数据订阅**: 使用主题订阅接口实时获取状态更新

6.  **远程脚本**: 使用9002端口进行远程脚本模式通信

### 1.3 通用请求格式

```json
{

"id": 请求ID, // 请求
    ID，用于标识请求，用户自定义，可以为数字或字符串，返回请求时原值返回

"ty": "请求类型", // 请求类型，由相应接口定义

"db": {} // 请求数据，具体内容由相应接口定义

}
```


### 1.4 通用响应格式

```json
{

"id": 请求ID, // 请求 ID，与请求参数一致

"ty": "请求类型", // 请求类型，与请求参数一致

"db": {}, // 返回数据，具体内容由相应接口定义

"err": "错误信息" // 如果请求失败，会有该字段，code
    是错误码，msg是具体的错误消息

}
```


接口没有数据返回时，默认返回数据如下，接口不再进行返回数据说明。

```json
{

"id": 请求ID, // 请求 ID，与请求参数一致

"ty": "请求类型" // 请求类型，与请求参数一致

}
```


## 2. 工程相关接口

### 2.1 运行脚本

**接口类型**: project/runScript

**功能**: 客户端直接发送脚本运行

**请求数据**:

```json
{

"id": 1,

"ty": "project/runScript",

"db": {

"scripts": {

"main": "主程序代码",

"subThreads": {"线程名": "线程代码"},

"subPrograms": {"程序名": "子程序代码"},

"interrupts": {"中断名": "中断程序代码"}

},

"vars": {// 可选参数，脚本共用变量，多脚本共享，同工程变量

"变量1": "值1", // key 为变量名，value为变量值

"变量2": "值2" // key 为变量名，value为变量值

}

}

}
```


**示例：**

```json
{

"id": 1,

"ty": "project/runScript",

"db": {

"scripts": {

"main": "print(v2)callSubprogram(\\sub1\\)",

"subPrograms": {"sub1": "print(v3)"}

},

"vars": {

"v1": 1,

"v2": "hello",

"v3": "HELLO"

}

}

}
```


**响应数据：**

```json
{

"id":1,

"ty":"project/runScript"

}
```


### 2.2 进入远程脚本模式

**接口类型**: project/enterRemoteScriptMode

**功能**: 进入远程脚本模式

**请求数据**:

```json
{

"id": 1,

"ty": "project/enterRemoteScriptMode"

}
```


**响应数据：**

```json
{

"id": 1,

"ty": "project/enterRemoteScriptMode"

}
```


### 2.3 运行工程（内部接口）

**接口类型**: project/run

**功能**: 运行指定工程

**注释:**需要注意的是，如果脚本设置了断点，当运行到断点处时，工程自动进入暂停状态。

> 工程ID需要导出当前脚本，解压Project.zip，projectlua下的文件夹名即为工程ID

**注: 如果发送的工程ID不对，web端会弹窗警告，但是接口不会返回错误信息**

**请求数据**:

```json
{

"id": 1,

"ty": "project/run",

"db": {

"id": "mhv9ubqz0pr69d5f" // 工程ID

}

}
```


**响应数据：**

```json
{

"id": 1,

"ty": "project/run"

}
```


### 2.4 通过工程映射索引号运行工程

**接口类型**: project/runByIndex

**功能**: 通过索引号运行已绑定的工程

**请求数据**:

```json
{

"id": 1,

"ty": "project/runByIndex",

"db": 1 // 工程映射索引号，int类型而非字符串

}
```


**响应数据：**

```json
{

"id": 1,

"ty": "project/runByIndex"

}
```


### 2.5 单步运行（内部接口）

**接口类型**: project/runStep

**功能**: 单步运行工程代码

**注释:**运行一行脚本，当没有工程在运行时，需传入工程
id，当工程暂停时，再次调该接口不需要传工程
id，工程执行一行代码后再次暂停。

单步运行时，只有主任务会根据该接口，一行一行的运行（调用一次运行一行），线程和中断会正常执行，所以工程会处于运行状态。

工程ID需要导出当前脚本，解压Project.zip，projectlua下的文件夹名即为工程ID

**请求数据**:

```json
{

"id": 1,

"ty": "project/runStep",

"db": {

"id": "mhv9ubqz0pr69d5f" // 工程ID

}

}
```


**响应数据：**

```json
{

"id": 1,

"ty": "project/runStep"

}
```


### 2.6 暂停工程

**接口类型**: project/pause

**功能**: 暂停正在运行的工程

**请求数据**:

```json
{

"id": 1,

"ty": "project/pause"

}
```


**响应数据：**

```json
{

"id": 1,

"ty": "project/pause"

}
```


### 2.7 恢复运行工程

**接口类型**: project/resume

**功能**: 恢复暂停的工程

**请求数据**:

```json
{

"id": 1,

"ty": "project/resume"

}
```


**响应数据：**

```json
{

"id": 1,

"ty": "project/resume"

}
```


### 2.8 停止运行工程

**接口类型**: project/stop

**功能**: 停止工程运行

**请求数据**:

```json
{

"id": 1,

"ty": "project/stop"

}
```


**响应数据：**

```json
{

"id": 1,

"ty": "project/stop"

}
```


### 2.9 设置断点(暂时无法使用)

**接口类型**: project/setBreakpoint

**功能**: 为脚本设置断点

**注：只允许主任务设置断点。当用户切换工程或重启后，断点数据需清除**。

> 该接口会覆盖设置对应脚本的断点。
>
> 如果要单独清除某个脚本的断点，可传递空数组。

**请求数据**:

```json
{

"id": 1, //请求id

"ty": "project/setBreakpoint",

"db": {

    "m8wope1d0tka199a":\[8,10,15\],//key为脚本id，value为数组，元素为行号

"m8wope1d0tka199b":\[20, 25\]

}

}
```


**响应数据：**

```json
{

"id": 1,

"ty": "project/setBreakpoint"

}
```


### 2.10 添加断点(暂时无法使用)

**接口类型**: project/addBreakpoint

**功能**: 添加断点(增加对应脚本的断点，即传入的与已有的合并)

**请求数据**:

```json
{

id: 1, //请求id

ty: "project/addBreakpoint",

db: {

m8wope1d0tka199a: \[8,10, 15\], //
    key为脚本id，value为数组，元素为行号

m8wope1d0tka199b: \[20, 25\]

}

}
```


**响应数据：**

```json
{

"id": 1,

"ty": "project/addBreakpoint"

}
```


### 2.11 删除断点(暂时无法使用)

**接口类型**: project/removeBreakpoint

**功能**: 停止工程运行

**请求数据**:

```json
{

id: 1, //请求id

ty: "project/removeBreakpoint",

db: {

m8wope1d0tka199a: \[8, 10, 15\], //
    key为脚本id，value为数组，元素为行号

m8wope1d0tka199b: \[20, 25\]

}

}
```


**响应数据：**

```json
{

"id": 1,

"ty": "project/removeBreakpoint"

}
```


### 2.12 清除所有断点(暂时无法使用)

**接口类型**: project/clearBreakpoint

**功能**: 停止工程运行

**请求数据**:

```json
{

"id": 1,

"ty": "project/clearBreakpoint"

}
```


**响应数据：**

```json
{

"id": 1,

"ty": "project/clearBreakpoint"

}
```


### 2.13 设置启动行

**接口类型**: project/setStartLine

**功能**: 设置主程序从哪一行开始执行

**注：只有主任务可以设置从哪一行开始运行，该设置会应用到下一次工程运行。且只生效一次。**

**请求数据**:

```json
{

"id": 1,

"ty": "project/setStartLine",

"db": 3 //行号

}
```


**响应数据：**

```json
{

"id": 1,

"ty": "project/setStartLine"

}
```


### 2.14 清除从指定行运行

**接口类型**: project/clearStartLine

**功能**: 清除之前设定的从指定行运行

**请求数据**:

```json
{

"id": 1,

"ty": "project/clearStartLine"

}
```


**响应数据：**

```json
{

"id": 1,

"ty": "project/clearStartLine",

}
```


## 3. 全局变量相关接口

### 3.1 全局变量定义

全局变量默认是掉电保存的，且运行时的值也会保留。即全局变量的值可由用户修改或运行时被修改，并且工程结束后值不会恢复到运行前，会保留当前值。

全局变量和工程变量的值以 json 字符串的形式保存。

下面是不同类型数据的示例，所有符号都必须是英文符号，不建议使用中文：

> 1\. 数字，直接输入数字即可：100 或 2.1
>
> 2\. 字符串，必须使用双引号：”abcas”
>
> 3\. 数组，使用中括号,：\[2,4.1,”abc”\]，\[\[1,2,3\],\[4,5,6\]\]
>
> 4\. Map：{“jp”:\[1,2,3,5,6,8\]}，{“a”:{“b”: 1}}

### 3.2 变量名命名规则

变量名需符合 lua 语法规范，及以字母或下划线开头。

避免使用双下划线开头，避免使用系统保留关键字及函数名。

主要保留字如下：

```json
"and", "break", "do", "else", "elseif", "end","false", "for",
    "function", "goto", "if", "in","local", "nil", "not", "or",
    "repeat", "return","then", "true", "until", "while", "table",
    "math","DO", "DOGroup", "DIO", "DIOGroup", "AO",
    "AIO","ModbusTCP","setSpeedJ", "setAccJ", "setSpeedL", "setAccL",
    "setBlender","setMoveRate","getCoor", "getTool", "setCoor",
    "editCoor", "setTool",
    "editTool","setPayload","enableVibrationSuppression",
    "disableVibrationSuppression","setCollisionDetectionSensitivity","initComplianceControl",
    "enableComplianceControl","disableComplianceControl","forceControlZeroCalibrate",
    "setFilterPeriod","searchSuccessed","getJoint", "getTCP", "getCoor",
    "getTool", "aposToCpos","cposToApos", "cposToCpos","posOffset",
    "posTrans", "coorRel", "toolRel",
    "getJointTorque","getJointExternalTorque","createTray",
    "getTrayPos", "posInverse", "distance",
    "interPos","planeTrans","getTrajStart", "getTrajEnd", "arrayAdd",
    "arraySub","coorTrans","movJ", "movL", "movC", "movCircle", "movLW",
    "movCW", "movTraj","setWeave", "weaveStart", "weaveEnd","setDO",
    "getDI", "getDO", "setDOGroup", "getDIGroup","getDOGroup", "setAO",
    "getAI", "getAO","getRegisterBool", "setRegisterBool",
    "getRegisterInt","setRegisterInt", "getRegisterFloat",
    "setRegisterFloat","RS485init", "RS485flush", "RS485write",
    "RS485read","readCoils", "readDiscreteInputs",
    "readHoldingRegisters","readInputRegisters","writeSingleCoil",
    "writeSingleRegister",
    "writeMultipleCoils","writeMultipleRegisters","createSocketClient",
    "connectSocketClient", "writeSocketClient","readSocketClient",
    "closeSocketClient","wait", "waitCondition", "systemTime",
    "stopProject","pauseProject", "runScript", "pauseScript",
    "resumeScript","stopScript", "callModule",
    "print","setInterruptInterval",
    "setInterruptCondition","clearInterrupt","strcmp",
    "strToNumberArray", "arrayToStr","enableMultiWeld", "getCurSeam",
    "isMultiWeldFinished","setMultiWeldOffset", "weldNextSeam",
    "resetMultiWeld","searchStart", "setMasterFlag", "getOffsetValue",
    "search","searchEnd", "searchOffset", "searchOffsetEnd",
    "searchError"
```


### 3.3 获取全局变量

**接口类型**: globalVar/getVars

**功能**: 获取所有全局变量

**请求数据**:

```json
{

"id": 1,

"ty": "globalVar/getVars"

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "globalVar/getVars",

"db": {

"Test_str": {

"val": "\\100000\\",

"nm": "这是一个字符串"

},

"ps1": {

"val": "{\\a\\:1}",

"nm": ""

},

"qqq": {

"val": 1,

"nm": ""

},

"v991": {

"val": "100",

"nm": " "

},

"v992": {

"val": "90.4",

"nm": " "

},

"v993": {

"val": "\[1,2,3,4,5\]",

"nm": " "

},

"v994": {

"val": "{\\aaa\\:100}",

"nm": " "

}

}

}
```


### 3.4 保存全局变量

**接口类型**: globalVar/saveVars

**功能**: 保存全局变量（增量保存）

**注释：**如果试图添加已存在的变量，该接口会更新同名变量的值

**请求数据**:

```json
{

"id": 1,

"ty": "globalVar/saveVars",

"db": {

"变量名": {

"nm": "变量备注", //不传则不处理

"val": "变量值"

}

}

}
```


**示例:**

```json
{

"id": 1,

"ty": "globalVar/saveVars",

"db": {

"Test_str": {

"val": "\\100000\\",

"nm": "这是一个字符串"

},

"v991": {

"val": "100",

"nm": "这是一个整数"

},

"v992": {

"val": "90.4",

"nm": "这是一个浮点数"

},

"v993": {

"val": "\[1, 2, 3, 4, 5\]",

"nm": "这是一个列表"

},

"v994": {

"val": "{\\aaa\\: 100}",

"nm": "这是一个键值对"

}

}

}
```


**响应数据:**

```json
{

"id": 1,

"ty": "globalVar/saveVars"

}
```


### 3.5 删除全局变量

**接口类型**: globalVar/removeVars

**功能**: 删除指定全局变量

**注释：**如果试图删除不存在的变量，该接口并不会报错

**请求数据**:

```json
{

"id": 1,

"ty": "globalVar/removeVars",

"db": \["v991", "v992"\] // 变量名列表

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "globalVar/removeVars"

}
```


## 4. 工程变量接口

### 4.1 获取当前所有工程变量值

**接口类型**: globalVar/GetProjectVarUpdate

**功能**: 获取工程运行时变量

**注释：**该接口必须在工程状态为运行时才有效，该接口不能获取全局变量，不能获取工程变量的注释

**请求数据**:

```json
{

"id": 1,

"ty": "globalVar/GetProjectVarUpdate"

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "globalVar/GetProjectVarUpdate",

"db": {

"project/point/p1": { //点位信息

"coord": 0,

"cp": \[216.2,-485.345,436.12,-175.22,1.657,-68.624\], //笛卡尔坐标

"ep": \[\],

"rj": \[-88.342,0.882,89.009,-3.283,86.059,-109.757\],

"tool": 0

},

"project/point/p2": { //点位信息

"coord": 0,

"ep": \[\],

"jp": \[-88.342,14.56,121.328,42.713,86.059,-109.757\], //关节角度

"tool": 0

},

"project/var/var1":"0",

}

}
```


## 5. 末端485接口

### 5.1 初始化

**接口类型**: EC2RS485/init

**功能**: 初始化末端485接口

**请求数据**:

```json
{

"id": 1,

"ty": "EC2RS485/init",

"db": {

"baudrate": 115200,
    //波特率:230400,128000,115200,57600,56000,38400,19200,14400,9600,4800,2400,1200,600,300,110

"stopBit": 1, //可选参数，停止位：1或2，默认1

"dataBit": 8, //可选参数，数据位：固定为8位

"parity": 0 //可选参数，校验位：0-无校验，1-奇校验，2-偶校验，默认0

}

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "EC2RS485/init"

}
```


### 5.2 清空缓存

**接口类型**: EC2RS485/flushReadBuffer

**功能**: 清空读取缓存

**请求数据**:

```json
{

"id": 1,

"ty": "EC2RS485/flushReadBuffer"

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "EC2RS485/flushReadBuffer"

}
```


### 5.3 读取数据

**接口类型**: EC2RS485/read

**功能**: 读取485数据

**请求数据**:

```json
{

"id": 1,

"ty": "EC2RS485/read",

"db": {

"length": 8, //读取字节数，最大128字节

"timeout": 3000
    //可选参数，读取超时时间，单位为毫秒，范围0~3000，默认3000

}

}
```


**响应数据**:

```json
{

"id":"m912rb1b0wsc2742",

"type": "EC2RS485/read",

"db":\[2,10\]
    //读取失败返回空数组，读取成功返回读取到的数据，数据为每个字节的无符号整数值

}
```


### 5.4 发送数据

**接口类型**: EC2RS485/write

**功能**: 通过485发送数据

**请求数据**:

```json
{

"id": 1,

"ty": "EC2RS485/write",

"db": \[2,10\]
    //要发送的数据，数据为每个字节的无符号整数值,最大长度为127

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "EC2RS485/write"

}
```


## 6. ModbusTCP主站接口

### 6.1 创建连接设备

**接口类型**: ModbusTcp/setDevice

**功能**: 创建ModbusTCP设备连接

**注释：**当试图创建同名设备时，会覆盖原先设备设置

**请求数据**:

```json
{

"id": 1,

"ty": "ModbusTcp/setDevice",

"db": {

"name": "deviceName",// 设备名称,唯一值

"ip": "192.168.1.100",// 设备 IP 地址

"port": 502,// 设备端口号

"slaveId": 1,// 从机地址

"endian": 1// 字节序：1-大端，2-小端，默认 1

}

}
```


**响应数据:**

```json
{

"id": 1,

"ty": "ModbusTcp/setDevice"

}
```


### 6.2 删除连接设备

**接口类型**: ModbusTcp/removeDevice

**功能**: 删除ModbusTCP设备

**注释：**当试图删除不存在设备时，该指令不会报错

**请求数据**:

```json
{

"id": 1,

"ty": "ModbusTcp/removeDevice",

"db": {

"name": "deviceName" //设备名称

}

}
```


**响应数据:**

```json
{

"id": 1,

"ty": "ModbusTcp/removeDevice"

}
```


### 6.3 创建/修改通信表

**接口类型**: ModbusTcp/setTable

**功能**: 创建或修改通信表

**注释：**如果试图在不存在的设备中创建表，该接口不会报错

**请求数据**:

```json
{

"id": 1,

"ty": "ModbusTcp/setTable",

"db": {

"name": "设备名", // 设备名

"tableName": "表名", // 表名，该设备下唯一

"functionCode": 1,// 功能码，支持 0x01，0x02，0x03，0x04，0x05，
    0x06，0x0F，0x10

"addr": 0, // 起始地址

"count": 10, // 读写地址数量

"period": 1000 // 通信周期，单位为毫秒，实际周期受通信链路负载影响

}

}
```


**响应数据:**

```json
{

"id": 1,

"ty": "ModbusTcp/setTable"

}
```


### 6.4 删除通信表

**接口类型**: ModbusTcp/removeTable

**功能**: 删除通信表

**注释：**如果试图在不存在的设备中删除表，或者删除不存在的表，该接口不会报错

**请求数据**:

```json
{

"id": 1,

"ty": "ModbusTcp/removeTable",

"db": {

"name": "deviceName", //设备名

"tableName":"tableName"//表名

}

}
```


**响应数据:**

```json
{

"id": 1,

"ty": "ModbusTcp/removeTable"

}
```


### 6.5 修改表的通信周期

**接口类型**: ModbusTcp/setPeriod

**功能**: 修改表的通信周期

**注释：**如果试图修改不存在的表，该接口不会报错

**请求数据**:

```json
{

"id": 1,

"ty": "ModbusTcp/setPeriod",

"db": {

"name": "deviceName", //设备名

"tableName":"tableName", //表名

"period":800//正整数，周期，单位为毫秒

}

}
```


**响应数据:**

```json
{

"id": 1,

"ty": "ModbusTcp/setPeriod"

}
```


### 6.6 给地址设置别名

**接口类型**: ModbusTcp/setName

**功能**: 给地址设置别名

**注释：**如果试图修改不存在的表，该接口不会报错

**请求数据**:

```json
{

"id": 1,

"ty": "ModbusTcp/setName",

"db": {

"name": "设备名", // 设备名

"tableName": "表名", // 表名，该设备下唯一

"addr": 0, // 地址

"alias": "flag" // 别名

}

}
```


**响应数据:**

```json
{

"id": 1,

"ty": "ModbusTcp/setName"

}
```


### 6.7 给地址段设置数据类型

**接口类型**: ModbusTcp/setType

**功能**: 给地址段设置数据类型

**注释：**如果试图修改不存在的表，该接口不会报错

> 只对保持和输入寄存器有效，对应功能码0x03,0x04,0x06,0x10。
>
> 默认数据类型是U16。

注意：0x06功能码只有一个地址，所以只能设置为I16或U16。

**请求数据**:

```json
{

"id": 1,

"ty": "ModbusTcp/setType",

"db": {

"name": "设备名", // 设备名

"tableName": "表名", // 表名，该设备下唯一

"type": "I32",//数据类型：I16,I32,I64,U16,U32,U64,F32,F64

"addr": 0, // 起始地址，一个地址对应两个字节长度，即16位

"count": 10 //
    地址数量，该数量应与对应的数据类型长度一致，可连续设置多组，例如将4个地址设置为两个U32类型数据

}

}
```


**响应数据:**

```json
{

"id": 1,

"ty": "ModbusTcp/setType"

}
```


### 6.8 修改地址的值

**接口类型**: ModbusTcp/setVal

**功能**: 修改地址的值

**注释：**只有写表的数据值可修改

**请求数据**:

```json
{

"id": 1,

"ty": "ModbusTcp/setVal",

"db": {

"name": "设备名", // 设备名

"tableName": "表名", // 表名，该设备下唯一

"addr": 0, // 地址，如果设置过数据类型，该地址须是该类型数据的首地址

"val":33 //该数据类型对应的值，线圈寄存器的值为0或

}

}
```


**响应数据:**

```json
{

"id": 1,

"ty": "ModbusTcp/setVal"

}
```


### 6.9 获取所有设备配置

**接口类型**: ModbusTcp/getConfig

**功能**: 获取所有设备配置

**请求数据**:

```json
{

"id": 1,

"ty": "ModbusTcp/getConfig",

}
```


**响应数据:**

```json
{

"id":1,

"ty":"ModbusTcp/getConfig",

"db":{

"deviceefx":{//设备名

"ip": "192.168.1.150",// IP

"port":502,//端口

"endian":1,//字节序：1-大端，0-小端

"slaveId": 1,//从机地址

"tables":{ //表配置

"table37b":{//表名

"functionCode": 16, //功能码

"addr":0,//起始地址

"count":10, //读写数量

"period": 1000, //通信周期，单位为毫秒

"alias":{//地址别名

"flag": 0// key为别名，value为地址

},

"val":
    \[//地址值，功能码为0x05,0x0F时，值为0或1，功能码为0x06,0x10时,值为U16类型，其他功能码无该字段

0,

8448,

0,

8448,

0,

0,

19713,

0,

0,

0

\],

    "dataFormat":{//数据类型,功能码为0x03,0x04,0x06,0x10时有效

"0":3,

1:0, //
    0无类型（与前面的子地址组合为其他类型）

"2":2, //
    1:I16,2:U16,3:I32,4:U32,5:I64,6:U64,7:F32,8:f64

"3":2,

"4":2,

"5":2,

"6":2,

"7":2,

"8":2,

"9":2

}

},

"tablez1q":{//表名

"functionCode": 1, //功能码

"addr":0,//起始地址

"count":10,//读写数量

"period": 800,//通信周期，单位为毫秒

"alias":{ //地址别名

"Name1": 15 // key为别名，value为地址

},

"val": \[\],

"dataFormat":{}

}

}

}

}

}
```


### 6.10 获取所有设备状态

**接口类型**: ModbusTcp/getState

**功能**: 获取所有设备状态

**请求数据**:

```json
{

"id": 1,

"ty": "ModbusTcp/getState"

}

}
```


**响应数据:**

```json
{

"id":1,

"ty":"ModbusTcp/getState",

"db":{

"deviceefx":{//设备名

"state":1, //连接状态，0：未连接1：已连接

"tables":{ //表数据

"table37b":{//表名

"syncCount": 1923,//同步次数

"syncError": 0, //同步错误次数

"val": \[//地址值

33, //该地址对应数据类型的值

"--",//该地址与上面的地址合并为新的数据类型

0,

33,

0,

0,

333,

0,

0,

0

\]

},

"tablez1q":{//表名

"syncCount": 3064,//同步次数

"syncError": 1,//同步错误次数

"val": \[//地址值

0,

1,

0,

0,

0,

0,

0,

0,

0,

0

\]

}

}

}

}

}
```


## 10. 机器人计算接口

### 10.1 正解

**接口类型**: Robot/apostocpos

**功能**: 关节空间到笛卡尔空间正解计算

注意

**请求数据**:

```json
{

"id": 1,

"ty": "Robot/apostocpos",

"db": {

"jp": \[10,20,30,40,50,60\], // 关节角,单位: deg

"coor": \[100,200,300,10,20,30\], // 用户坐标系

"tool": \[100,200,300,10,20,30\], // 工具坐标系

"ep": \[\]

}

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "Robot/apostocpos",

"db": \[100,200,300,10,20,30\] // 笛卡尔坐标

}
```


### 10.2 逆解

**接口类型**: Robot/cpostoapos

**功能**: 笛卡尔空间到关节空间逆解计算

**注意：**参考关节角默认为\[20，20，20，20，20，20\]，如果返回值为空，尝试修改rj参数

**请求数据**:

```json
{

"id": 1,

"ty": "Robot/cpostoapos",

"db": {

"cp": \[100,200,300,40,50,60\], //末端位置,单位: mm, deg

"rj": \[10,20,30,40,50,60\], //参考关节角,单位: deg

"ep": \[\] //可选,附加轴位置

}

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "Robot/cpostoapos",

"db": \[10,20,30,10,20,30\] //逆解后的关节角,单位: deg

}
```


### 10.3 笛卡尔坐标偏移计算

**接口类型**: Robot/calculateRelativePose

**功能**: 笛卡尔坐标偏移计算

**请求数据**:

```json
{

"id": 1,

"ty": "Robot/calculateRelativePose",

"db": {

"pos": \[485.447, -256.717, 63.845, 179.968, 2.951,
    -90.062\], // 当前末端TCP坐标\[x,y,z,a,b,c\], 单位：毫米和度

"posCoor": \[-159.108, 378.109, 145.576, 0.086, -0.032,
    0.110\], //
    可选参数，默认为世界坐标系，当前末端TCP坐标系\[x,y,z,a,b,c\],
    单位：毫米和度

"offset": \[10, 0, 0, 0, 0, 0\], // 偏移量\[x,y,z,a,b,c\],
    单位：毫米和度

"coorType": "tool", // 坐标系类型，可选值："user"或"tool"

"coor": \[0, 0, 0, 0, 0, 0\] //
    可选参数，coorType为user时有效，偏移坐标系，默认世界坐标系

}

}

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "Robot/calculateRelativePose",

"db": \[-159.108, 378.109, 145.576, 0.086, -0.032, 0.110\] //
    偏移后的坐标\[x,y,z,a,b,c\], 单位：毫米和度，

//
    如果传了posCoor，则该坐标在posCoor坐标系下，否则在世界坐标系下

}
```


## 11. 机器人运动控制接口

### 11.1 点动

**接口类型**: Robot/jog

**功能**: 启动机器人点动

**请求数据**:

```json
{

"id": 1,

"ty": "Robot/jog",

"db": {

"mode": 2, //1：关节点动 2：直线点动

"speed": -0.1, //速度，取值范围-1~1

"index": 3,//
    关节序号，如果是关节角度1~6代表轴1~轴6，如果是直线点动，则依次为xyzabc

"coorType": 0, // 坐标系类型 0：用户坐标系，1：工具坐标系

"coorId": 1 //用户坐标系id

}

}
```


**注意**: 需要每500ms调用点动心跳接口维持点动

**响应数据**:

```json
{

"id": 1,

"ty": "Robot/jog"

}
```


### 11.2 停止点动

**接口类型**: Robot/stopJog

**功能**: 停止点动

**请求数据**:

```json
{

"id": 1,

"ty": "Robot/stopJog"

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "Robot/stopJog"

}
```


### 11.3 点动心跳

**接口类型**: Robot/jogHeartbeat

**功能**: 维持点动状态，需在使用点动功能后每隔0.5s发送一次

**请求数据**:

```json
{

"id": 1,

"ty": "Robot/jogHeartbeat"

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "Robot/jogHeartbeat"

}
```


### 11.4 moveTo

**接口类型**: Robot/moveTo

**功能**: 运动到指定位置

**注意**: 启动RunTo后需要每隔0.5S发送一次心跳接口维持点动

**请求数据**:

```json
{

"id": 1,

"ty": "Robot/moveTo",

"db": {

"type": 0,// 0=Home 位置, 1=安全位置,
    2=蜡烛位，3=打包位，4=关节规划到指定位置，5=直线规划到指定位置，6=程序恢复点

"target": { // 可选，目标位置，仅当 type=4 或 5 时使用该字段

"cp": \[x,y,z,a,b,c\], // 末端位置

"jp": \[0,0.1,0.2,0.3,0.4,0.5\], //关节位置

"ep": \[\] //外部轴位置

}

}

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "Robot/moveTo"

}
```


### 11.5 moveTo心跳

**接口类型**: Robot/moveToHeartbeat

**功能**: 维持RunTo运动，启动RunTo后需要每隔0.5S发送一次心跳接口维持点动

**请求数据**:

```json
{

"id": 1,

"ty": "Robot/moveToHeartbeat"

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "Robot/moveToHeartbeat"

}
```


### 11.6 设置手动运动倍率

**接口类型**: Robot/setManualMoveRate

**请求数据**:

```json
{

"id": 1,

"ty": "Robot/setManualMoveRate",

"db": 70// 速度百分比， 1~100

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "Robot/setManualMoveRate"

}
```


### 11.7 设置自动运动倍率

**接口类型**: Robot/setAutoMoveRate

**请求数据**:

```json
{

"id": 1,

"ty": "Robot/setAutoMoveRate",

"db": 70// 速度百分比， 1~100

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "Robot/setAutoMoveRate"

}
```


### 11.8 运动指令

**接口类型**: Robot/move

movC必须传入笛卡尔坐标点，不能使用关节角度点

**注意：可选值如果不需要请不要传入该字段，目前已知bug，如果传入**

**"coor": \[\],"tool": \[\],两个空数组，后端会崩溃**

**请求数据**:

```json
{

"id": 1,

"ty": "Robot/move",

"db": \[ //
    运动指令列表，一次发多条可以保证指令之间的过渡，多次请求之间的过渡不能保证

{

"type": "movJ", //
    运动类型，movJ：关节运动，movL：直线运动，movC：圆弧运动，movCircle：圆周运动

"circleNum": 2, //
    可选参数，当type为movCircle时有效，指定圆周运动的圆数，默认为1

"speed": 60, //
    运动速度，关节空间运动时单位：度/秒，笛卡尔空间运动时单位：毫米/秒

"acc": 150, //
    加速度，关节空间运动时单位：度/秒^2，笛卡尔空间运动时单位：毫米/秒^2

"blend": 20, // 过渡半径，单位：毫米

"relativeBlend": 20, // 相对过渡，百分比，   
    0~100，blend存在时，该参数不生效

"targetPoint": { //
    目标点，jp和cp至少需要有一个，jp优先级更高

"jp": \[10, 20, 30, 40, 50, 60\], //
    关节角，单位：度

"cp": \[100, 200, 300, 10, 20, 30\], //
    笛卡尔坐标，单位：毫米和度

"rj": \[10, 20, 30, 40, 50, 60\], //
    参考关节角，可选，单位：度, 用于逆解计算

"ep": \[\] // 可选, 附加轴位置

},

"middlePoint": { //
    中间点,当type为movC和movCircle时有效且必传

"cp": \[100, 200, 300, 10, 20, 30\], //
    笛卡尔坐标，单位：毫米和度

"rj": \[10, 20, 30, 40, 50, 60\] //
    参考关节角，可选，单位：度, 用于逆解计算

},

"coor": \[100, 200, 300, 10, 20, 30\], //
    坐标系\[x,y,z,a,b,c\], 可选，默认使用当前坐标系, 单位：毫米和度

"tool": \[100, 200, 300, 10, 20, 30\] //
    工具坐标系\[x,y,z,a,b,c\], 可选，默认使用当前工具, 单位：毫米和度

}


\]

}
```


**响应数据**:

返回说明：指令接收后，接口即正常返回，指令是否运行正常需实时查看机器人状态和系统错误。

```json
{

"id": 1,

"ty": "Robot/move"

}
```


### 11.9 暂停运动

**接口类型**: Robot/pause

**请求数据**:

```json
{

"id": 1,

"ty": "Robot/pause"

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "Robot/pause"

}
```


### 11.10 恢复运动

**接口类型**: Robot/resume

**请求数据**:

```json
{

"id": 1,

"ty": "Robot/resume"

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "Robot/resume"

}
```


### 11.11 停止运动

**接口类型**: Robot/stopMove

**请求数据**:

```json
{

"id": 1,

"ty": "Robot/stopMove"

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "Robot/stopMove"

}
```


## 12. 机器人控制命令

### 12.1 上使能

**接口类型**: Robot/switchOn

**请求数据**:

```json
{

"id": 1,

"ty": "Robot/switchOn"

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "Robot/switchOn"

}
```


### 12.2 下使能

**接口类型**: Robot/switchOff

**请求数据**:

```json
{

"id": 1,

"ty": "Robot/switchOff"

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "Robot/switchOff"

}
```


### 12.3 进入手动模式

**接口类型**: Robot/toManual

**仅2.3.2.6以上版本可用**

注意：该接口无法直接从远程模式跳转至手动模式

**请求数据**:

```json
{

"id": 1,

"ty": "Robot/toManual"

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "Robot/toManual"

}
```


### 12.4 进入自动模式

**接口类型**: Robot/toAuto

**仅2.3.2.6以上版本可用**

**请求数据**:

```json
{

"id": 1,

"ty": "Robot/toAuto"

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "Robot/toAuto"

}
```


### 12.5 进入远程模式

**接口类型**: Robot/toRemote

**仅2.3.2.6以上版本可用**

注意：该接口无法直接从手动模式跳转至远程模式

**请求数据**:

```json
{

"id": 1,

"ty": "Robot/toRemote"

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "Robot/toRemote"

}
```


### 12.6 进入救援模式(异常)

**接口类型**: Robot/switchOnRescue

**请求数据**:

```json
{

"id": 1,

"ty": "Robot/switchOnRescue"

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "Robot/switchOnRescue"

}
```


### 12.7 进入仿真模式

**接口类型**: Robot/toSimulation

**请求数据**:

```json
{

"id": 1,

"ty": "Robot/toSimulation"

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "Robot/toSimulation"

}
```


### 12.8 进入实机模式

**接口类型**: Robot/toActual

**请求数据**:

```json
{

"id": 1,

"ty": "Robot/toActual"

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "Robot/toActual"

}
```


### 12.9 进入拖拽模式

**接口类型**: Robot/startDrag

**仅2.3.2.6以上版本可用**

注意：只可在远程模式和手动模式下使用

**请求数据**:

```json
{

"id": 1,

"ty": "Robot/startDrag"

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "Robot/startDrag"

}
```


### 12.10 退出拖拽模式

**接口类型**: Robot/stopDrag

**仅2.3.2.6以上版本可用**

注意：只可在远程模式和手动模式下使用

**请求数据**:

```json
{

"id": 1,

"ty": "Robot/stopDrag"

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "Robot/stopDrag"

}
```


### 12.11 清除错误

**接口类型**: System/clearError

**请求数据**:

```json
{

"id": 1,

"ty": "System/clearError"

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "System/clearError"

}
```


## 13. IO相关接口

### 13.1 获取IO值

**接口类型**: IOManager/GetIOValue

**功能**: 获取多个IO的当前值

**请求数据**:

```json
{

"id": 1,

"ty": "IOManager/GetIOValue",

"db": \[ // 传入要查询的 IO 的类型和端口号

{"type": "DI", "port": 0},

{"type": "DO", "port": 10},

{"type": "AI", "port": 1},

{"type": "AO", "port": 2}

\]

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "IOManager/GetIOValue",

"db": \[

{"type": "DI", "port": 0, "value": 0},

{"type": "DO", "port": 10, "value": 1},

{"type": "AI", "port": 1, "value": 2.2},

{"type": "AO", "port": 2, "value": 4.44}

\]

}
```


### 13.2 写入IO值

**接口类型**: IOManager/SetIOValue

**功能**: 设置IO输出值

**请求数据**:

```json
{

"id": 1,

"ty": "IOManager/SetIOValue",

"db": {"type": "DO", "port": 10, "value": 1}

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "IOManager/SetIOValue"

}
```


## 14. 寄存器相关接口

### 14.1 获取寄存器值

**接口类型**: RegisterManager/GetRegisterValue

**功能**: 获取寄存器值

**请求数据**:

```json
{

"id": 1,

"ty": "RegisterManager/GetRegisterValue",

"db": \[10000, 20000\] // 传入地址

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "RegisterManager/GetRegisterValue",

"db": \[

{"address": 10000, "value": 0},

{"address": 20000, "value": 0}

\]

}
```


### 14.2 写入寄存器值

**接口类型**: RegisterManager/SetRegisterValue

**功能**: 设置寄存器值

**请求数据**:

```json
{

"id": 1,

"ty": "RegisterManager/SetRegisterValue",

"db": {"address": 10000, "value": 0}

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "RegisterManager/SetRegisterValue"

}
```


### 14.3 设置扩展数组数据类型

**接口类型**: RegisterManager/setExtendArrayType

**请求数据**:

```json
{

"id": 1,

"ty": "RegisterManager/setExtendArrayType",

"db": {

"index": 999, // 数组索引 0-999

"type": "Bool" //
    支持的类型：Bool、UInt8、Int8、UInt16、Int16、UInt32、Int32、Float32

}

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "RegisterManager/setExtendArrayType"

}
```


### 14.4 删除扩展数组索引

**接口类型:** RegisterManager/removeExtendArray

**该接口会重置该索引数据，同时不再列表中展示。**

**请求数据**:

```json
{

"id": 1,

"ty": "RegisterManager/removeExtendArray",

"db": {

"index": 999, // 数组索引 0-999

}

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "RegisterManager/removeExtendArray"

}
```


## 15. 主题订阅/推送接口

### 15.1 主题订阅接口

**接口类型**: publish/topic

**功能**: 订阅数据推送主题

**注：**

1\. 订阅的数据只有在数据发生变化或开始订阅时推送。

2\. 受数据本身变化周期影响，正常情况下数据实际推送周期会大于订阅周期。

**请求数据**:

```json
{

"ty": "publish/topic", // 其中 topic 为实际要订阅的主题名称

"tc": 0 // 可选参数， 订阅周期，单位为毫秒，默认
    0，实际推送周期受主题本身数据变化周期影响

}
```


**响应数据**:

```json
{

"ty": "publish/topic", // 与订阅名称一致

"db": {} // 推送数据，具体内容由主题决定

}
```


### 15.2 工程状态

**主题名称**: publish/ProjectState

推送当前工程状态

**推送数据**:

```json
{

ty: "publish/ProjectState",

db: {

id: "mhv9ubqz0pr69d5f", // 工程id

state: 3, //
    工程状态，0：空闲，1：正在加载工程，2：正在运行，3：暂停

isStep: false, // 是否单步运行

projectType: 0, // 工程类型，0：普通工程 1：远程执行脚本
    2：远程进入远程脚本模式

scripts: { // 脚本数据，state 为 2 或 3 时，才有该字段

m8wope1d0tka199a: { // 脚本 id

line: 8 // 脚本当前正在执行的行号

}

}  

}

}
```


### 15.3 变量数据主题

**主题名称**: publish/VarUpdate

**注意：**当工程运行时，全局变量和工程变量变化时推送。只推送变化的变量。

**推送数据**:

```json
{

"ty": "publish/VarUpdate",

"db": {

"global/var/bool1": "34",// key 为 {定义域}/{类型}/{变量名}

"project/var/dvs": "3"

}

}
```


推送数据如上，下面对 key 的 3 个部分进行说明：

1\. 定义域：global 表示是全局变量，project 表示是工程变量

2\. 类型：var 表示是普通变量，point 表示是点变量

3\. 变量名：变量的 key 值，不是“nm“

### 15.4 机器人状态主题

**主题名称**: publish/RobotStatus

**注意：**程序处于自动运行状态，state=2

**推送数据**:

```json
{

"ty": "publish/RobotStatus",

"db": {

"mode": 0, // 0=手动; 1=自动; 2=远程

"state": 0, // 0=未使能; 1=使能中; 2=空闲; 3=点动中;
    4=RunTo; 5=拖动中

"isMoving": 0, //机械臂是否正在运动

"moveRate": 1, // 自动运行速度倍率

"manualMoveRate": 0.3, // 手动运行速度倍率

"recoveryState": 0,    // 传送带状态

"isSimulation": true, // 是否仿真模式

"teachingPendant": 0, // 是否使用示教器

"rescueFlag": 0,

"modeSwitch": 0,

"ToolId": 0, // 当前工具 ID

"PayloadId": 0, // 当前负载 ID

"CoordinateId": 1, // 当前坐标系 ID

"defaultToolId": 0, // 默认工具 ID

"defaultPayloadId": 0, // 默认负载 ID

"defaultUserCoorId": 1, // 默认用户坐标系 ID

"type": "S20-180-ECO-V2", // 机器人型号

"stateName": "未使能",

"runDuration": 1374 // 运行时间

}

}
```


### 15.5 机器人位姿主题

**主题名称**: publish/RobotPosture

**推送数据**:

```json
{

"ty": "publish/RobotPosture",

"db": {

"joint": \[ 0,0.0,90.0,0.0,0.0,0.0 \], // 关节位置(单位:
    角度)

"end": { // 关节位置(单位: 毫米, 角度)

"x": 203.002,

"y": 1206.332,

"z": 1066.0,

"a": 0.0,

"b": 90.0,

"c": 93.432,

"mode": -1

},

"ep": \[\] // 附加轴位置

}

}
```


### 15.6 机器人坐标系主题

**主题名称**: publish/RobotCoordinate

**推送数据**:

```json
{

"ty": "publish/RobotCoordinate",

"db": {

"tool": { // 工具坐标系

"x": 0.0,

"y": 0.0,

"z": 0.0,

"a": 0.0,

"b": 0.0,

"c": 0.0

},

"user": { // 用户坐标系

"x": 700.0000000000003,

"y": -770.0,

"z": 0.0,

"a": 0.0,

"b": 0.0,

"c": 0.0

}

}

}
```


### 15.7 系统日志主题

**主题名称**: publish/Log

**推送数据**:

```json
{

"ty": "publish/Log",

"db": \[

\[6,13561,1760946003.582,"机器人发生\<腕关节\>奇异."\],

\[6,13552,1760946003.582,"机器人构型获取失败."\],

\[6,13552,1760946003.582,"机器人构型获取失败."\],

\[6,13566,1760946003.582,"解析解逆解失败, 末端目标位姿:
    \[0.8463706694236185,0.5380104024137184, 1.066, 0,
    1.5707963267948966, 1.7468025738248967\], 构型: -1."\],

\[4,2023,1760946003.582,"奇异位置."\]

}
```


### 15.8 系统错误主题

**主题名称**: publish/Error

**推送数据**:

```json
{

"ty": "publish/Error",

"db": \[

\[4,2023,1760946003.582,"奇异位置."\]

}
```


## 16. 远程脚本模式接口

### 16.1 进入方式

> 1.通过2.2进入
>
> 2.运行脚本时，在主任务脚本中调用 enterRemoteScriptMode()指令

### 16.2 通信方式

使用 TCP/IP 协议，机器人控制器作为服务端，端口号为 9002。控制器默认IP
地址为 192.168.1.136，若重新配置过 IP，则使用配置后的 IP 进行连接。

为方便数据解析，API 接口统一采用 Json 字符串进行数据通信，仅支持
UTF8编码。

### 16.3 接口说明

**通信端口**: 9002

**请求数据**:

```json
{

"command": "resume", // 控制命令，当存在此字段时，其他字段无效//
    可选值：resume: 恢复运行,stop：停止运行, interrupt：中断当前指令

"script": "print(6)", // 要执行的脚本代码

"vars": \["P1", "v1"\], //
    可选参数，执行完脚本后，将这些变量的值返回，如果工程被 stop
    停止，则不返回

"...": "..." // 自定义参数，例如"id": "mdo8zdy30wscc06e"

}
```


**响应数据**:

```json
{

"code": 0, // 0 表示成功，其他表示失败

"msg": "OK", // 错误信息

"vars": {

"P1": 1, // 脚本执行后，返回的变量值

"v2": "hello"

},

"...": "..." // 自定义参数会原值返回

}
```


### 16.4 运行机制

> 1\. 通过上面的接口发送的脚本会被加入到运行队列中，按顺序执行，队列长度
> 64，队列满了之后会返回错误。
>
> 2\. 每个请求中，脚本内定义的 local
> 类型的变量只在当前的指令脚本中生效。其他变量将持续生效。
>
> 3\. 可用指令与正常编写脚本相同。
>
> 4\. 如果执行类似 while(true)这种不会退出的脚本，可通过发送 interrupt
> 请求打断运行。
>
> 5\. 因为远程脚本模式是在工程运行状态下执行的，可通过 2
> 中的相关工程运行控制指令来暂停、恢复或停止工程。

## 17.CRI实时控制接口(Codroid RealTime Interface)

### 17.1 实时数据定义

mask是无符号16位数，下面对位0~15进行说明，对应的位为1时表示要推送，为0时表示不推送，同时说明推送的数据。

实际推送的数据根据需要推送的数据按顺序拼接，实际推送的数据大小会动态变化，用户需根据配置自行判断每个字节的内容。

<table style="width:100%;">
<colgroup>
<col style="width: 11%" />
<col style="width: 15%" />
<col style="width: 19%" />
<col style="width: 52%" />
</colgroup>
<tbody>
<tr>
<td style="text-align: left;">比特位</td>
<td style="text-align: left;">字段</td>
<td style="text-align: left;">数据类型</td>
<td style="text-align: left;">推送数据说明</td>
</tr>
<tr>
<td style="text-align: left;">0</td>
<td style="text-align: left;">时间戳</td>
<td style="text-align: left;">Int64</td>
<td style="text-align: left;">毫秒数时间戳</td>
</tr>
<tr>
<td style="text-align: left;">1</td>
<td style="text-align: left;">状态数据1</td>
<td style="text-align: left;">UInt16</td>
<td style="text-align: left;">具体说明参考下表</td>
</tr>
<tr>
<td style="text-align: left;">2</td>
<td style="text-align: left;">状态数据2</td>
<td style="text-align: left;">UInt16</td>
<td style="text-align: left;">具体说明参考下表</td>
</tr>
<tr>
<td style="text-align: left;">3~7</td>
<td style="text-align: left;">保留位</td>
<td style="text-align: left;"></td>
<td style="text-align: left;"></td>
</tr>
<tr>
<td style="text-align: left;">8</td>
<td style="text-align: left;">关节位置</td>
<td style="text-align: left;">Float32/Float64</td>
<td
style="text-align: left;">关节0~关节N（实际关节数量）的位置，单位rad</td>
</tr>
<tr>
<td style="text-align: left;">9</td>
<td style="text-align: left;">关节速度</td>
<td style="text-align: left;">Float32/Float64</td>
<td
style="text-align: left;">关节0~关节N（实际关节数量）的速度，单位rad/s</td>
</tr>
<tr>
<td style="text-align: left;">10</td>
<td style="text-align: left;">末端位置</td>
<td style="text-align: left;">Float32/Float64</td>
<td style="text-align: left;"><p>x,y,z：单位m</p>
<p>rx,ry,rz: 单位rad</p>
<p>如果是7轴，还有e：单位rad</p></td>
</tr>
<tr>
<td style="text-align: left;">11</td>
<td style="text-align: left;">末端速度</td>
<td style="text-align: left;">Float32/Float64</td>
<td style="text-align: left;"><p>x,y,z：单位m/s</p>
<p>rx,ry,rz: 单位rad/s</p></td>
</tr>
<tr>
<td style="text-align: left;">12</td>
<td style="text-align: left;">末端线速度</td>
<td style="text-align: left;">Float32/Float64</td>
<td style="text-align: left;">TCP的线速度，单位m/s</td>
</tr>
<tr>
<td style="text-align: left;">13</td>
<td style="text-align: left;">关节输出力矩</td>
<td style="text-align: left;">Float32/Float64</td>
<td
style="text-align: left;">关节0~关节N（实际关节数量）的输出力矩，单位Nm</td>
</tr>
<tr>
<td style="text-align: left;">14</td>
<td style="text-align: left;">关节受到外力</td>
<td style="text-align: left;">Float32/Float64</td>
<td
style="text-align: left;">关节0~关节N（实际关节数量）的受到外力，单位Nm</td>
</tr>
<tr>
<td style="text-align: left;">15</td>
<td style="text-align: left;">外部轴位置</td>
<td style="text-align: left;">Float32/Float64</td>
<td
style="text-align: left;">外部轴0~外部轴N（实际外部轴数量）的位置，单位与外部轴类型相关，一般来说旋转轴是rad，直线轴是m</td>
</tr>
</tbody>
</table>

> 状态数据1为UInt16类型，共16位，每一位代表不同的系统状态标志，具体含义如下表所示：

|        |          |          |
|:-------|:---------|:---------|
| 比特位 | 低8位    | 高8位    |
| 0      | 工程运行 | 碰撞停止 |
| 1      | 工程停止 | 在安全位 |
| 2      | 工程暂停 | 有报警   |
| 3      | 使能中   | 仿真模式 |
| 4      | 未使能   | 急停按下 |
| 5      | 手动模式 | 救援模式 |
| 6      | 拖动中   | 自动模式 |
| 7      | 运动中   | 远程模式 |

> 状态数据2为UInt16类型，高8位是实时控制接口的错误码，为UInt8类型，低8位定义如下

|        |              |
|:-------|:-------------|
| 比特位 | 低8位        |
| 0      | 实时控制模式 |
| 1      | 保留         |
| 2      | 保留         |
| 3      | 保留         |
| 4      | 保留         |
| 5      | 保留         |
| 6      | 保留         |
| 7      | 保留         |

1.  // 机器人指令数据流

2.  struct CommandData {

3.  Int64 timestamp{0}; // 目前版本未使用

4.  Float64 position\[6\]{0}; // 关节或末端位置

5.  UInt8 type{0}; // 0: 关节, 1: 末端

6.  UInt8 nc\[7\]{0}; // 保留字节

7.  };

### 17.2 开启数据流推送（2.3.3.23以下）

**数据流通信协议：UDP**

**接口类型**: CRI/StartDataPush

**功能**: 开启数据推送

**请求数据**:

```json
{

"id": 1,

"ty": "CRI/StartDataPush",

"db": {

"ip": "192.168.1.200", // 填写推送目标地址

"port": 10086, // 填写推送目标端口，合法范围为10000-65534

"duration": 1 // 数据推送间隔, 单位: ms, 范围: \>=1整数

}

}
```


**响应数据**:

```json
{   

"id":1,

"ty":"CRI/StartDataPush",

"db":null

}
```


### 17.3 关闭数据流推送（2.3.3.23以下）

**数据流通信协议：UDP**

**接口类型**: CRI/StopDataPush

**功能**: 开启数据推送

**请求数据**:

```json
{

"id": 1,

"ty": "CRI/StopDataPush"

}
```


**响应数据**:

```json
{

"id":1,

"ty":"CRI/StopDataPush",

"db":null

}
```


### 17.4 开启数据流推送（2.3.3.23以上，包括2.3.3.23）

**数据流通信协议：UDP**

**接口类型**: CRI/StartDataPush

**功能**: 开启数据推送

**请求数据**:

```json
{

"id": 1,

"ty": "CRI/StartDataPush",

"db": {

"ip": "192.168.1.150", // udp服务IP

"port": 18888, // udp服务端口，10000~65534

"duration": 1000, // 推送周期，单位毫秒，1~1000,
    可不传，默认1

"highPercision": true, //
    浮点数是否使用double（8字节），可不传，默认使用float（4字节）

"mask": 0xFFFF, // 设置要推送的数据，可不传，默认是0xFFFF

}

}
```


**响应数据**:

```json
{

"id":1,

"ty":"CRI/StartDataPush"

}
```


### 17.5 关闭数据流推送（2.3.3.23以上，包括2.3.3.23）

**数据流通信协议：UDP**

**接口类型**: CRI/StopDataPush

**功能**: 开启数据推送

**请求数据**:

```json
{

"id": 1,

"ty": "CRI/StopDataPush",

"db": { // 当只有一个服务推送时，该参数可不传，否则必须要传

"ip": "192.168.1.150", // udp服务IP

"port": 18888, // udp服务端口，10000~65534

}

}
```


**响应数据**:

```json
{

"id":1,

"ty":"CRI/StopDataPush"

}
```


### 17.6开启实时控制

**数据流通信协议：UDP**

**接口类型**: CRI/StartControl

**功能**: 开启数据推送

**请求数据**:

```json
{

"id": 1,

"ty": "CRI/StartControl",

"db": {

"filterType": 0, // 0-关闭滤波 1-平均滤波值 2-二阶低通滤波
    3-椭圆滤波

"duration": 1, // 指令间隔, 单位: ms, 范围: \[1, 16\]整数

"startBuffer": 3 // 启动缓冲点数量, 范围: \[1-100\]整数,
    当接受到至少该数量的点位时, 机器人才会开始运动

}

}
```


**响应数据**:

```json
{

"id":1,

"ty":"CRI/StartControl"

}
```


### 17.7 关闭实时控制

**数据流通信协议：UDP**

**接口类型**: CRI/StopControl

**功能**: 开启数据推送

**请求数据**:

```json
{

"id": 1,

"ty": "CRI/StopControl"

}
```


**响应数据**:

```json
{

"id":1,

"ty":"CRI/StopControl"

}
```


## 18 NexCobot相关接口

### 18.1获取配置

**接口类型:** NexCobot/getConfig

**请求数据**:

```json
{

"id": 1,

"ty": "NexCobot/getConfig",

"db": "SDD" // 配置名称, "RSP" 或 "SDD"

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "NexCobot/getConfig",

"db": {

"name": "SDD",

"description": "Safety Function in EtherCAT Data Offset Define",

"signature": "FSoE_SDD",

"version": "1.1.1.1",

"ceTableIndex": 61984,

"coeTableBufferSize": 16128,

"parameters": \[

{

"index": 20480,

"subIndex": 1,

"dataType": 8,

"bitLength": 32,

"caption1": "RSAP_Infomation(FSoE)",

"caption2": "FSoE Master",

"caption3": "FSoE Master to Drive 1",

"caption4": "FSoE Master to Drive 1 STO state",

"description": "Select safety data offset",

"unit": "NaN",

"access": "RW",

"editor": "",

"value": 0,

"min": 0,

"max": 2147483647

}

\]

}

}
```


### 18.2 应用修改

**接口类型:** NexCobot/apply

**请求数据**:

```json
{

"id": 1,

"ty": "NexCobot/apply",

"db": {

"name": "SDD",

"parameters": \[

{

"index": 1000,

"subIndex": 1,

"value": 100

}

\]

}

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "NexCobot/apply",

"db": true // 布尔值，true：应用成功，false：应用失败

}
```


### 18.3 确认下发

**接口类型:** NexCobot/confirm

**请求数据**:

```json
{

"id": 1,

"ty": "NexCobot/confirm",

"db": ""

}
```


**响应数据**:

1.  

## 19. 机器人设置相关接口说明

### 19.1设置碰撞检测灵敏度

**仅2.3.2.10以上版本可用**

**接口类型:** Robot/setCollisionSensitivity

**请求数据**:

```json
{

"id": 1,

"ty": "Robot/setCollisionSensitivity",

"db": 100 // 灵敏度, 0-100

}
```


**响应数据**:

```json
{

"id":1,

"ty":"Robot/setCollisionSensitivity",

"db":true

}
```


### 19.2设置负载

**接口类型:** Robot/setPayload

**仅2.3.2.10以上版本可用**

**请求数据**:

```json
{

"id": 1,

"ty": "Robot/setPayload",

"db": 1 // 负载id, 0-15

}
```


**响应数据**:

```json
{

"id":1,

"ty":"Robot/setPayload",

"db":null

}
```


## 20. 从站配置相关接口

### 20.1获取从站配置信息

**仅2.3.3.23以上版本可用**

**接口类型:** RegisterCommunicator/GetConfiguration

**请求数据**:

```json
{

"id": 1,

"ty": "RegisterCommunicator/GetConfiguration",

"db": ""

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "RegisterCommunicator/GetConfiguration",

"db": {

"enable": true, // 是否启用

"enableHeartBeatDetection": false, // 是否启用心跳检测

"heartBeatDetectionDuration": 1000, // 心跳检测间隔

"addressList": { // 寄存器地址列表

"input": { // 输入

"list": { // 列表

"0": { // 地址

"name": "reserved", // 名称

"groupName": "Base", // 组名

"type": "UInt16", // 类型

"length": 2 // 长度

},

"2": {

"name": "heartBeatFromMaster",

"groupName": "Base",

"type": "UInt16",

"length": 2

},

//...

},

"totalLength": 180 // 总长度

},

"output": { // 输出寄存器

"list": {

"0": {

"name": "reserved",

"groupName": "Base",

"type": "UInt8",

"length": 1

},

"1": {

"name": "majorVersion",

"groupName": "Base",

"type": "UInt8",

"length": 1

},

// ...

},

"totalLength": 304 // 总长度

}

},

"method": "ModbusTCP", // 当前使用的通信协议

"methodRange": \[ // 支持的通信协议

"ModbusTCP",

"Anybus",

"Estun",

"Profinet",

"EthernetIP"

\],

"ModbusTCP": {

"address": "192.168.1.136:502", // 通信地址

"version": "2.3" // 协议版本

},

"Anybus": {

"bigEndian": true, // 是否使用大端模式

"version": "2.3" // 协议版本

},

"Estun": {

"bigEndian": true, // 是否使用大端模式

"version": "2.3" // 协议版本

},

"Profinet": {

"bigEndian": true, // 是否使用大端模式

"ip": "192.168.0.136", // ip地址

"netMask": "255.255.255.0", // 子网掩码

"gateway": "0.0.0.0", // 网关

"deviceId": 136, // 设备号

"selectedInputAddrs": \[ // 选中的输入寄存器地址

0,

2,

// ...

\],

"selectedOutputAddrs": \[ // 选中的输出寄存器地址

0,

1,

// ...

\],

"selectedInputLength": 180, // 选中的输入寄存器总长度

"selectedOutputLength": 304 // 选中的输出寄存器总长度

},

"EthernetIP": {

"bigEndian": true, // 是否使用大端模式

"ip": "192.168.0.136", // ip地址

"netMask": "255.255.255.0", // 子网掩码

"gateway": "0.0.0.0", // 网关

"deviceId": 136, // 设备号

"selectedInputAddrs": \[ // 选中的输入寄存器地址

0,

2,

// ...

\],

"selectedOutputAddrs": \[ // 选中的输出寄存器地址

0,

1,

// ...

\],

"selectedInputLength": 180, // 选中的输入寄存器总长度

"selectedOutputLength": 304 // 选中的输出寄存器总长度

}

}

}
```


### 20.2导出GSDML文件

**接口类型:** RegisterCommunicator/ExportGSDML

**仅2.3.3.23以上版本可用**

**请求数据**:

```json
{

"id": 1,

"ty": "RegisterCommunicator/exportGSDML",

"db": ""

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "RegisterCommunicator/exportGSDML",

"db": {

"file": ".....", // 文件内容

"filename": "xxx.xml" // 文件名

}

}
```


### 20.3导出EDS文件

**接口类型:** RegisterCommunicator/exportEDS

**仅2.3.3.23以上版本可用**

**请求数据**:

```json
{

"id": 1,

"ty": "RegisterCommunicator/exportEDS",

"db": ""

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "RegisterCommunicator/exportEDS",

"db": {

"file": ".....", // 文件内容

"filename": "xxx.xml" // 文件名

}

}
```


## 21. 法兰灯带控制接口

### 21.1灯带普通控制接口

**仅2.3.3.23以上版本可用**

**接口类型:** MFC/SetLed

**请求数据**:

```json
{

"id": 1,

"ty": "MFC/SetLed",

"db": {

"type": 1, // 接口类型，1：普通模式 2：高级模式

"duration": 10000, // 持续时间，单位：ms

"color": "green" //
    颜色，可选值：red、white、green、blue、yellow、greenBlink、blueBlink、yellowBlink

}

}
```


**响应数据**:

```json
{

"id":1,

"ty":"MFC/SetLed",

"db":""

}
```


### 21.2灯带高级控制接口

**接口类型:** MFC/SetLed

**仅2.3.3.23以上版本可用**

**请求数据**:

```json
{

"id": 1,

"ty": "MFC/SetLed",

"db": {

"type": 1, // 接口类型，1：普通模式 2：高级模式

"duration": 10000, // 持续时间，单位：ms

"color": {

"mode": 3, // 控制模式 0：常亮 1：呼吸 2：闪烁1 3：闪烁2
    4：流水灯 5：关灯

"color1": \[255, 255, 0, 255\], // 颜色1 \[R(红), G(绿),
    B(蓝), brightness(亮度)\]

"timer1": 500, // 时间1，单位：ms

"color2": \[0, 0, 255, 255\], // 颜色2

"timer2": 500, // 时间2

}

}

}
```


**响应数据**:

```json
{

"id":1,

"ty":"MFC/SetLed",

"db":null

}
```


> 控制模式参考以下说明：

1.  常亮模式，mode==0

> 需要设置color1

2.  呼吸模式，mode==1

> 可以一种颜色也可以两种，一种颜色只设置color1和timer1，两种颜色则color1,timer1,color2,timer2都要设置。
>
> 注意：呼吸时间与timer和亮度都有关系，参考下图

<img src="abb_media/media/image2.png"
style="width:5.76389in;height:2.37734in" alt="HCR24KJGADQBS" />

3.  闪烁模式1，mode==2

> 设置两种颜色交替显示，参考下图：

<img src="abb_media/media/image3.png"
style="width:5.76389in;height:2.27851in" alt="HS424KJGADABW" />

4.  闪烁模式2，mode==3

> 与闪烁模式1类似，但是再切换颜色之间会关灯，timer定义不同，参考下图：

<img src="abb_media/media/image4.png"
style="width:5.76389in;height:2.41896in" alt="SHAK4KJGADQA6" />

5.  流水灯模式，mode==4

流水等状态下，单独控制每一个灯的亮度，会以蓝绿色，每次四个循环点亮led。

该模式只传mode即可。

6.  关灯，mode==5

> 灯灭，只传mode即可。

## 23. 焊接接口(目前版本2.3.3.8)

### 23.1获取试运行状态

**接口类型:** welder/getTestModeState

**请求数据**:

```json
{

"id": 1,

"ty": "welder/getTestModeState",

"db": ""

}
```


**响应数据**:

```json
{

"id":1,

"ty":"welder/getTestModeState",

"db":0 // 1为启动试运行，0为取消试运行

}
```


### 23.2更改试运行状态

**接口类型:** welder/sendparams

**请求数据**:

```json
{

"id": 1,

"ty": "welder/sendparams",

"db": \[{

"path": "Welder/testMode",

"value": 1 // 1为启动试运行，0为取消试运行

}\]

}
```


**响应数据**:

```json
{

"id":1,

"ty":"welder/sendparams",

"db":null

}
```


### 23.3 送丝

**接口类型:** welder/sendparams

**请求数据**:

```json
{

"id":1,

"ty":"welder/sendparams",

"db":\[{

"path":"Welder/command",

"value":1

}\]

}
```


**响应数据**:

```json
{

"id":1,

"ty":"welder/sendparams",

"db":null

}
```


### 23.4 退丝

**接口类型:** welder/sendparams

**请求数据**:

```json
{

"id":1,

"ty":"welder/sendparams",

"db":\[{

"path":"Welder/command",

"value":2

}\]

}
```


**响应数据**:

```json
{

"id":1,

"ty":"welder/sendparams",

"db":null

}
```


### 23.5 送气

**接口类型:** welder/sendparams

**请求数据**:

```json
{

"id":1,

"ty":"welder/sendparams",

"db":\[{

"path":"Welder/command",

"value":3

}\]

}
```


**响应数据**:

```json
{

"id":1,

"ty":"welder/sendparams",

"db":null

}
```


### 23.6 清除错误

**接口类型:** welder/sendparams

**请求数据**:

```json
{

"id":1,

"ty":"welder/sendparams",

"db":\[{

"path":"Welder/command",

"value":4

}\]

}
```


**响应数据**:

```json
{

"id":1,

"ty":"welder/sendparams",

"db":null

}
```


### 23.7 送丝，退丝，送气心跳

**接口类型:** welder/sendparams

每隔500ms发送一次

**请求数据**:

```json
{

"id": 1,

"ty": "welder/sendparams",

"db": \[{

"path": "Welder/commandHeart",

"value": 1774944290274}\]

}
```


**响应数据**:

```json
{

"id":1,

"ty":"welder/sendparams",

"db":null

}
```


### 23.8 停止送丝，退丝，送气

**接口类型:** welder/sendparams

**请求数据**:

```json
{

"id":1,

"ty":"welder/sendparams",

"db":\[{

"path":"Welder/command",

"value":0

}\]

}
```


**响应数据**:

```json
{

"id":1,

"ty":"welder/sendparams",

"db":null

}
```


### 23.9 获取单道焊缝工艺模板

**接口类型:** welder/getSingleWeldTemplateList

返回一个单道焊缝工艺模板json

**请求数据**:

```json
{

"id":1,

"ty":"welder/getSingleWeldTemplateList",

"db":""

}
```


**响应数据**:

```json
{

"id":1,

"ty":"welder/getSingleWeldTemplateList",

"db":

\[

{

"tmpname": "Template Name",

"id": 1,

"params": \[

{

"function": "speed",

"label": \[

"speed",

"速度"

\],

"value": 0,

"rule": {

"unit": "mm/s",

"min": -65535,

"max": 65535

}

},

{

"function": "wtype",

"label": \[

"wtype",

"摆动样式"

\],

"value": 0,

"data": \[

{

"label": \[

"Triangle",

"锯齿摆"

\],

"value": 0

},

{

"label": \[

"Sine",

"正弦摆"

\],

"value": 1

},

{

"label": \[

"Crescent",

"月牙摆"

\],

"value": 2

},

{

"label": \[

"Spatial Triangle",

"空间三角摆"

\],

"value": 3

}

\]

},

{

"function": "wfreq",

"label": \[

"wfreq",

"摆动频率"

\],

"value": 1,

"rule": {

"unit": "Hz",

"min": 0,

"max": 65535

}

},

{

"function": "wamp",

"label": \[

"wamp",

"摆动幅度"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "left",

"label": \[

"left",

"左停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "right",

"label": \[

"right",

"右停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "middle",

"label": \[

"middle",

"中间停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "wrotanglex",

"label": \[

"wrotanglex",

"操作角"

\],

"value": 0,

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

},

{

"function": "wrotanglez",

"label": \[

"wrotanglez",

"摆动角"

\],

"value": 0,

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

},

{

"function": "sagitta",

"label": \[

"sagitta",

"弦高"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "direction",

"label": \[

"direction",

"摆动方向"

\],

"value": 1,

"data": \[

{

"label": \[

"Positive Crescent",

"正月牙"

\],

"value": 1

},

{

"label": \[

"Negative Crescent",

"反月牙"

\],

"value": -1

}

\]

}

\]

},

{

"tmpname": "Template Name",

"id": 2,

"params": \[

{

"function": "speed",

"label": \[

"speed",

"速度"

\],

"value": 0,

"rule": {

"unit": "mm/s",

"min": -65535,

"max": 65535

}

},

{

"function": "wtype",

"label": \[

"wtype",

"摆动样式"

\],

"value": 0,

"data": \[

{

"label": \[

"Triangle",

"锯齿摆"

\],

"value": 0

},

{

"label": \[

"Sine",

"正弦摆"

\],

"value": 1

},

{

"label": \[

"Crescent",

"月牙摆"

\],

"value": 2

},

{

"label": \[

"Spatial Triangle",

"空间三角摆"

\],

"value": 3

}

\]

},

{

"function": "wfreq",

"label": \[

"wfreq",

"摆动频率"

\],

"value": 1,

"rule": {

"unit": "Hz",

"min": 0,

"max": 65535

}

},

{

"function": "wamp",

"label": \[

"wamp",

"摆动幅度"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "left",

"label": \[

"left",

"左停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "right",

"label": \[

"right",

"右停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "middle",

"label": \[

"middle",

"中间停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "wrotanglex",

"label": \[

"wrotanglex",

"操作角"

\],

"value": 0,

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

},

{

"function": "wrotanglez",

"label": \[

"wrotanglez",

"摆动角"

\],

"value": 0,

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

},

{

"function": "sagitta",

"label": \[

"sagitta",

"弦高"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "direction",

"label": \[

"direction",

"摆动方向"

\],

"value": 1,

"data": \[

{

"label": \[

"Positive Crescent",

"正月牙"

\],

"value": 1

},

{

"label": \[

"Negative Crescent",

"反月牙"

\],

"value": -1

}

\]

}

\]

}

\]

}
```


### 23.10 保存单道焊缝工艺模板

**接口类型:** welder/setSingleWeld

单道焊缝工艺模板为数组，如需保存多个，添加多个模板对象到数组中

**请求数据**:

```json
{

"id":1,

"ty":"welder/setSingleWeld",

"db":\[

{

"tmpname": "Template Name",    // 工艺模板名称

"id": 4,                       // 工艺模板ID

"params": \[

{

"function": "speed",

"label": \[

"speed",

"速度"

\],

"value": 0,                // 速度值

"rule": {

"unit": "mm/s",

"min": -65535,

"max": 65535

}

},

{

"function": "wtype",

"label": \[

"wtype",

"摆动样式"

\],

"value": 0,                // 0：锯齿摆 1：正弦摆 2：月牙摆
    3：空间三角摆

"data": \[

{

"label": \[

"Triangle",

"锯齿摆"

\],

"value": 0

},

{

"label": \[

"Sine",

"正弦摆"

\],

"value": 1

},

{

"label": \[

"Crescent",

"月牙摆"

\],

"value": 2

},

{

"label": \[

"Spatial Triangle",

"空间三角摆"

\],

"value": 3

}

\]

},

{

"function": "wfreq",

"label": \[

"wfreq",

"摆动频率"

\],

"value": 1,                // 摆动频率 单位：Hz

"rule": {

"unit": "Hz",

"min": 0,

"max": 65535

}

},

{

"function": "wamp",

"label": \[

"wamp",

"摆动幅度"

\],

"value": 0,            // 摆动幅度 单位：mm

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "left",

"label": \[

"left",

"左停留"

\],

"value": 0,            // 左停留时长 单位：ms

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "right",

"label": \[

"right",

"右停留"

\],

"value": 0,            // 右停留时长 单位：ms

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "middle",

"label": \[

"middle",

"中间停留"

\],

"value": 0,            // 中间停留时长 单位：ms

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "wrotanglex",

"label": \[

"wrotanglex",

"操作角"

\],

"value": 0,            // 操作角 单位：角度

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

},

{

"function": "wrotanglez",

"label": \[

"wrotanglez",

"摆动角"

\],

"value": 0,            // 摆动角 单位：角度

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

},

{

"function": "sagitta",

"label": \[

"sagitta",

"弦高"

\],

"value": 0,            // 弦高 单位：mm

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "direction",

"label": \[

"direction",

"摆动方向"

\],

"value": 1,        // 摆动方向 1：正月牙 -1：反月牙

"data": \[

{

"label": \[

"Positive Crescent",

"正月牙"

\],

"value": 1

},

{

"label": \[

"Negative Crescent",

"反月牙"

\],

"value": -1

}

\]

}

\]

}

\]

}
```


**响应数据**:

```json
{

"id":1,

"ty":"welder/setSingleWeld",

"db": ""

}
```


### 23.11 下发单道焊缝工艺模板

**接口类型:** welder/sendTemplateParams

单道焊缝工艺模板为数组，如需保存多个，添加多个模板对象到数组中

**请求数据**:

```json
{

"id":1,

"ty":"welder/sendTemplateParams",

"db":\[

{

"tmpname": "Template Name", // 工艺模板名称

"id": 4, // 工艺模板ID

"params": \[

{

"function": "speed",

"label": \[

"speed",

"速度"

\],

"value": 0, // 速度值

"rule": {

"unit": "mm/s",

"min": -65535,

"max": 65535

}

},

{

"function": "wtype",

"label": \[

"wtype",

"摆动样式"

\],

"value": 0, // 0：锯齿摆 1：正弦摆 2：月牙摆 3：空间三角摆

"data": \[

{

"label": \[

"Triangle",

"锯齿摆"

\],

"value": 0

},

{

"label": \[

"Sine",

"正弦摆"

\],

"value": 1

},

{

"label": \[

"Crescent",

"月牙摆"

\],

"value": 2

},

{

"label": \[

"Spatial Triangle",

"空间三角摆"

\],

"value": 3

}

\]

},

{

"function": "wfreq",

"label": \[

"wfreq",

"摆动频率"

\],

"value": 1, // 摆动频率 单位：Hz

"rule": {

"unit": "Hz",

"min": 0,

"max": 65535

}

},

{

"function": "wamp",

"label": \[

"wamp",

"摆动幅度"

\],

"value": 0, // 摆动幅度 单位：mm

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "left",

"label": \[

"left",

"左停留"

\],

"value": 0, // 左停留时长 单位：ms

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "right",

"label": \[

"right",

"右停留"

\],

"value": 0, // 右停留时长 单位：ms

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "middle",

"label": \[

"middle",

"中间停留"

\],

"value": 0, // 中间停留时长 单位：ms

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "wrotanglex",

"label": \[

"wrotanglex",

"操作角"

\],

"value": 0, // 操作角 单位：角度

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

},

{

"function": "wrotanglez",

"label": \[

"wrotanglez",

"摆动角"

\],

"value": 0, // 摆动角 单位：角度

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

},

{

"function": "sagitta",

"label": \[

"sagitta",

"弦高"

\],

"value": 0, // 弦高 单位：mm

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "direction",

"label": \[

"direction",

"摆动方向"

\],

"value": 1, // 摆动方向 1：正月牙 -1：反月牙

"data": \[

{

"label": \[

"Positive Crescent",

"正月牙"

\],

"value": 1

},

{

"label": \[

"Negative Crescent",

"反月牙"

\],

"value": -1

}

\]

}

\]

}

\]

}
```


**响应数据**:

```json
{

"id":1,

"ty":"welder/sendTemplateParams",

"db": ""

}
```


### 23.12 获取多层多道工艺模板

**接口类型:** welder/getMultiWeldTemplateList

返回一个多层多道工艺模板json

**请求数据**:

```json
{

"id":1,

"ty":"welder/getMultiWeldTemplateList",

"db":""

}
```


**响应数据**:

```json
{

"id":1,

"ty":"welder/getMultiWeldTemplateList",

"db":

\[

{

"tmpname": "Template Name",

"id": 1,

"params": \[

{

"function": "speed",

"label": \[

"speed",

"速度"

\],

"value": 0,

"rule": {

"unit": "mm/s",

"min": -65535,

"max": 65535

}

},

{

"function": "wtype",

"label": \[

"wtype",

"摆动样式"

\],

"value": 0,

"data": \[

{

"label": \[

"Triangle",

"锯齿摆"

\],

"value": 0

},

{

"label": \[

"Sine",

"正弦摆"

\],

"value": 1

},

{

"label": \[

"Crescent",

"月牙摆"

\],

"value": 2

},

{

"label": \[

"Spatial Triangle",

"空间三角摆"

\],

"value": 3

}

\]

},

{

"function": "wfreq",

"label": \[

"wfreq",

"摆动频率"

\],

"value": 1,

"rule": {

"unit": "Hz",

"min": 0,

"max": 65535

}

},

{

"function": "wamp",

"label": \[

"wamp",

"摆动幅度"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "left",

"label": \[

"left",

"左停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "right",

"label": \[

"right",

"右停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "middle",

"label": \[

"middle",

"中间停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "wrotanglex",

"label": \[

"wrotanglex",

"操作角"

\],

"value": 0,

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

},

{

"function": "wrotanglez",

"label": \[

"wrotanglez",

"摆动角"

\],

"value": 0,

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

},

{

"function": "sagitta",

"label": \[

"sagitta",

"弦高"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "direction",

"label": \[

"direction",

"摆动方向"

\],

"value": 1,

"data": \[

{

"label": \[

"Positive Crescent",

"正月牙"

\],

"value": 1

},

{

"label": \[

"Negative Crescent",

"反月牙"

\],

"value": -1

}

\]

}

\]

},

{

"tmpname": "Template Name",

"id": 2,

"params": \[

{

"function": "speed",

"label": \[

"speed",

"速度"

\],

"value": 0,

"rule": {

"unit": "mm/s",

"min": -65535,

"max": 65535

}

},

{

"function": "wtype",

"label": \[

"wtype",

"摆动样式"

\],

"value": 0,

"data": \[

{

"label": \[

"Triangle",

"锯齿摆"

\],

"value": 0

},

{

"label": \[

"Sine",

"正弦摆"

\],

"value": 1

},

{

"label": \[

"Crescent",

"月牙摆"

\],

"value": 2

},

{

"label": \[

"Spatial Triangle",

"空间三角摆"

\],

"value": 3

}

\]

},

{

"function": "wfreq",

"label": \[

"wfreq",

"摆动频率"

\],

"value": 1,

"rule": {

"unit": "Hz",

"min": 0,

"max": 65535

}

},

{

"function": "wamp",

"label": \[

"wamp",

"摆动幅度"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "left",

"label": \[

"left",

"左停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "right",

"label": \[

"right",

"右停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "middle",

"label": \[

"middle",

"中间停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "wrotanglex",

"label": \[

"wrotanglex",

"操作角"

\],

"value": 0,

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

},

{

"function": "wrotanglez",

"label": \[

"wrotanglez",

"摆动角"

\],

"value": 0,

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

},

{

"function": "sagitta",

"label": \[

"sagitta",

"弦高"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "direction",

"label": \[

"direction",

"摆动方向"

\],

"value": 1,

"data": \[

{

"label": \[

"Positive Crescent",

"正月牙"

\],

"value": 1

},

{

"label": \[

"Negative Crescent",

"反月牙"

\],

"value": -1

}

\]

}

\]

}

\]

}
```


### 23.13 保存多层多道工艺模板

**接口类型:** welder/setMultiWeld

多层多道工艺模板为数组，如需保存多个，添加多个模板对象到数组中

**请求数据**:

```json
{

"id": 1,

"ty": "welder/setMultiWeld",

"db": \[

{

"tmpname": "Template Name",     // 模板一名称

"id": 1,                        // 模板ID

"params": {

"th": \[

{

"function": "speed",

"label": \[

"speed",

"速度"

\]

},

{

"function": "wtype",

"label": \[

"wtype",

"摆动样式"

\]

},

{

"function": "wfreq",

"label": \[

"wfreq",

"摆动频率"

\]

},

{

"function": "wamp",

"label": \[

"wamp",

"摆动幅度"

\]

},

{

"function": "left",

"label": \[

"left",

"左停留"

\]

},

{

"function": "right",

"label": \[

"right",

"右停留"

\]

},

{

"function": "middle",

"label": \[

"middle",

"中间停留"

\]

},

{

"function": "wrotanglex",

"label": \[

"wrotanglex",

"操作角"

\]

},

{

"function": "wrotanglez",

"label": \[

"wrotanglez",

"摆动角"

\]

},

{

"function": "sagitta",

"label": \[

"sagitta",

"弦高"

\]

},

{

"function": "direction",

"label": \[

"direction",

"摆动方向"

\]

},

{

"function": "xOffset",

"label": \[

"xOffset",

"x偏移"

\]

},

{

"function": "yOffset",

"label": \[

"yOffset",

"y偏移"

\]

},

{

"function": "zOffset",

"label": \[

"zOffset",

"z偏移"

\]

},

{

"function": "aOffset",

"label": \[

"aOffset",

"a偏移"

\]

}

\],

"td": \[                              // 焊缝数组     

\[                                // 焊缝一

{

"function": "speed",

"label": \[

"speed",

"速度"

\],

"value": 0,                //焊缝一速度

"rule": {

"unit": "mm/s",

"min": -65535,

"max": 65535

}

},

{

"function": "wtype",

"label": \[

"wtype",

"摆动样式"

\],

"value": 0,     //焊缝一摆动样式

"data": \[

{

"label": \[

"Triangle",

"锯齿摆"

\],

"value": 0

},

{

"label": \[

"Sine",

"正弦摆"

\],

"value": 1

},

{

"label": \[

"Crescent",

"月牙摆"

\],

"value": 2

},

{

"label": \[

"Spatial Triangle",

"空间三角摆"

\],

"value": 3

}

\]

},

{

"function": "wfreq",

"label": \[

"wfreq",

"摆动频率"

\],

"value": 1,

"rule": {

"unit": "Hz",

"min": 0,

"max": 65535

}

},

{

"function": "wamp",

"label": \[

"wamp",

"摆动幅度"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "left",

"label": \[

"left",

"左停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "right",

"label": \[

"right",

"右停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "middle",

"label": \[

"middle",

"中间停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "wrotanglex",

"label": \[

"wrotanglex",

"操作角"

\],

"value": 0,

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

},

{

"function": "wrotanglez",

"label": \[

"wrotanglez",

"摆动角"

\],

"value": 0,

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

},

{

"function": "sagitta",

"label": \[

"sagitta",

"弦高"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "direction",

"label": \[

"direction",

"摆动方向"

\],

"value": 1,

"data": \[

{

"label": \[

"Positive Crescent",

"正月牙"

\],

"value": 1

},

{

"label": \[

"Negative Crescent",

"反月牙"

\],

"value": -1

}

\]

},

{

"function": "xOffset",

"label": \[

"xOffset",

"x偏移"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "yOffset",

"label": \[

"yOffset",

"y偏移"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "zOffset",

"label": \[

"zOffset",

"z偏移"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "aOffset",

"label": \[

"aOffset",

"a偏移"

\],

"value": 0,

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

}

\],

\[                            // 焊缝二

{

"function": "speed",

"label": \[

"speed",

"速度"

\],

"value": 0,

"rule": {

"unit": "mm/s",

"min": -65535,

"max": 65535

}

},

{

"function": "wtype",

"label": \[

"wtype",

"摆动样式"

\],

"value": 0,

"data": \[

{

"label": \[

"Triangle",

"锯齿摆"

\],

"value": 0

},

{

"label": \[

"Sine",

"正弦摆"

\],

"value": 1

},

{

"label": \[

"Crescent",

"月牙摆"

\],

"value": 2

},

{

"label": \[

"Spatial Triangle",

"空间三角摆"

\],

"value": 3

}

\]

},

{

"function": "wfreq",

"label": \[

"wfreq",

"摆动频率"

\],

"value": 1,

"rule": {

"unit": "Hz",

"min": 0,

"max": 65535

}

},

{

"function": "wamp",

"label": \[

"wamp",

"摆动幅度"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "left",

"label": \[

"left",

"左停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "right",

"label": \[

"right",

"右停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "middle",

"label": \[

"middle",

"中间停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "wrotanglex",

"label": \[

"wrotanglex",

"操作角"

\],

"value": 0,

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

},

{

"function": "wrotanglez",

"label": \[

"wrotanglez",

"摆动角"

\],

"value": 0,

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

},

{

"function": "sagitta",

"label": \[

"sagitta",

"弦高"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "direction",

"label": \[

"direction",

"摆动方向"

\],

"value": 1,

"data": \[

{

"label": \[

"Positive Crescent",

"正月牙"

\],

"value": 1

},

{

"label": \[

"Negative Crescent",

"反月牙"

\],

"value": -1

}

\]

},

{

"function": "xOffset",

"label": \[

"xOffset",

"x偏移"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "yOffset",

"label": \[

"yOffset",

"y偏移"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "zOffset",

"label": \[

"zOffset",

"z偏移"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "aOffset",

"label": \[

"aOffset",

"a偏移"

\],

"value": 0,

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

}

\],

\[                                // 焊缝三

{

"function": "speed",

"label": \[

"speed",

"速度"

\],

"value": 0,

"rule": {

"unit": "mm/s",

"min": -65535,

"max": 65535

}

},

{

"function": "wtype",

"label": \[

"wtype",

"摆动样式"

\],

"value": 0,

"data": \[

{

"label": \[

"Triangle",

"锯齿摆"

\],

"value": 0

},

{

"label": \[

"Sine",

"正弦摆"

\],

"value": 1

},

{

"label": \[

"Crescent",

"月牙摆"

\],

"value": 2

},

{

"label": \[

"Spatial Triangle",

"空间三角摆"

\],

"value": 3

}

\]

},

{

"function": "wfreq",

"label": \[

"wfreq",

"摆动频率"

\],

"value": 1,

"rule": {

"unit": "Hz",

"min": 0,

"max": 65535

}

},

{

"function": "wamp",

"label": \[

"wamp",

"摆动幅度"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "left",

"label": \[

"left",

"左停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "right",

"label": \[

"right",

"右停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "middle",

"label": \[

"middle",

"中间停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "wrotanglex",

"label": \[

"wrotanglex",

"操作角"

\],

"value": 0,

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

},

{

"function": "wrotanglez",

"label": \[

"wrotanglez",

"摆动角"

\],

"value": 0,

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

},

{

"function": "sagitta",

"label": \[

"sagitta",

"弦高"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "direction",

"label": \[

"direction",

"摆动方向"

\],

"value": 1,

"data": \[

{

"label": \[

"Positive Crescent",

"正月牙"

\],

"value": 1

},

{

"label": \[

"Negative Crescent",

"反月牙"

\],

"value": -1

}

\]

},

{

"function": "xOffset",

"label": \[

"xOffset",

"x偏移"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "yOffset",

"label": \[

"yOffset",

"y偏移"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "zOffset",

"label": \[

"zOffset",

"z偏移"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "aOffset",

"label": \[

"aOffset",

"a偏移"

\],

"value": 0,

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

}

\]

\]

}

},

{                                    // 模板二

"tmpname": "Template Name",

"id": 2,

"params": {

"th": \[

{

"function": "speed",

"label": \[

"speed",

"速度"

\]

},

{

"function": "wtype",

"label": \[

"wtype",

"摆动样式"

\]

},

{

"function": "wfreq",

"label": \[

"wfreq",

"摆动频率"

\]

},

{

"function": "wamp",

"label": \[

"wamp",

"摆动幅度"

\]

},

{

"function": "left",

"label": \[

"left",

"左停留"

\]

},

{

"function": "right",

"label": \[

"right",

"右停留"

\]

},

{

"function": "middle",

"label": \[

"middle",

"中间停留"

\]

},

{

"function": "wrotanglex",

"label": \[

"wrotanglex",

"操作角"

\]

},

{

"function": "wrotanglez",

"label": \[

"wrotanglez",

"摆动角"

\]

},

{

"function": "sagitta",

"label": \[

"sagitta",

"弦高"

\]

},

{

"function": "direction",

"label": \[

"direction",

"摆动方向"

\]

},

{

"function": "xOffset",

"label": \[

"xOffset",

"x偏移"

\]

},

{

"function": "yOffset",

"label": \[

"yOffset",

"y偏移"

\]

},

{

"function": "zOffset",

"label": \[

"zOffset",

"z偏移"

\]

},

{

"function": "aOffset",

"label": \[

"aOffset",

"a偏移"

\]

}

\],

"td": \[                            // 模板二焊缝一

\[

{

"function": "speed",

"label": \[

"speed",

"速度"

\],

"value": 0,

"rule": {

"unit": "mm/s",

"min": -65535,

"max": 65535

}

},

{

"function": "wtype",

"label": \[

"wtype",

"摆动样式"

\],

"value": 0,

"data": \[

{

"label": \[

"Triangle",

"锯齿摆"

\],

"value": 0

},

{

"label": \[

"Sine",

"正弦摆"

\],

"value": 1

},

{

"label": \[

"Crescent",

"月牙摆"

\],

"value": 2

},

{

"label": \[

"Spatial Triangle",

"空间三角摆"

\],

"value": 3

}

\]

},

{

"function": "wfreq",

"label": \[

"wfreq",

"摆动频率"

\],

"value": 1,

"rule": {

"unit": "Hz",

"min": 0,

"max": 65535

}

},

{

"function": "wamp",

"label": \[

"wamp",

"摆动幅度"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "left",

"label": \[

"left",

"左停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "right",

"label": \[

"right",

"右停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "middle",

"label": \[

"middle",

"中间停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "wrotanglex",

"label": \[

"wrotanglex",

"操作角"

\],

"value": 0,

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

},

{

"function": "wrotanglez",

"label": \[

"wrotanglez",

"摆动角"

\],

"value": 0,

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

},

{

"function": "sagitta",

"label": \[

"sagitta",

"弦高"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "direction",

"label": \[

"direction",

"摆动方向"

\],

"value": 1,

"data": \[

{

"label": \[

"Positive Crescent",

"正月牙"

\],

"value": 1

},

{

"label": \[

"Negative Crescent",

"反月牙"

\],

"value": -1

}

\]

},

{

"function": "xOffset",

"label": \[

"xOffset",

"x偏移"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "yOffset",

"label": \[

"yOffset",

"y偏移"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "zOffset",

"label": \[

"zOffset",

"z偏移"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "aOffset",

"label": \[

"aOffset",

"a偏移"

\],

"value": 0,

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

}

\],

\[                                // 模板二焊缝二

{

"function": "speed",

"label": \[

"speed",

"速度"

\],

"value": 0,

"rule": {

"unit": "mm/s",

"min": -65535,

"max": 65535

}

},

{

"function": "wtype",

"label": \[

"wtype",

"摆动样式"

\],

"value": 0,

"data": \[

{

"label": \[

"Triangle",

"锯齿摆"

\],

"value": 0

},

{

"label": \[

"Sine",

"正弦摆"

\],

"value": 1

},

{

"label": \[

"Crescent",

"月牙摆"

\],

"value": 2

},

{

"label": \[

"Spatial Triangle",

"空间三角摆"

\],

"value": 3

}

\]

},

{

"function": "wfreq",

"label": \[

"wfreq",

"摆动频率"

\],

"value": 1,

"rule": {

"unit": "Hz",

"min": 0,

"max": 65535

}

},

{

"function": "wamp",

"label": \[

"wamp",

"摆动幅度"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "left",

"label": \[

"left",

"左停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "right",

"label": \[

"right",

"右停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "middle",

"label": \[

"middle",

"中间停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "wrotanglex",

"label": \[

"wrotanglex",

"操作角"

\],

"value": 0,

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

},

{

"function": "wrotanglez",

"label": \[

"wrotanglez",

"摆动角"

\],

"value": 0,

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

},

{

"function": "sagitta",

"label": \[

"sagitta",

"弦高"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "direction",

"label": \[

"direction",

"摆动方向"

\],

"value": 1,

"data": \[

{

"label": \[

"Positive Crescent",

"正月牙"

\],

"value": 1

},

{

"label": \[

"Negative Crescent",

"反月牙"

\],

"value": -1

}

\]

},

{

"function": "xOffset",

"label": \[

"xOffset",

"x偏移"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "yOffset",

"label": \[

"yOffset",

"y偏移"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "zOffset",

"label": \[

"zOffset",

"z偏移"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "aOffset",

"label": \[

"aOffset",

"a偏移"

\],

"value": 0,

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

}

\],

\[                                // 模板二焊缝三

{

"function": "speed",

"label": \[

"speed",

"速度"

\],

"value": 0,

"rule": {

"unit": "mm/s",

"min": -65535,

"max": 65535

}

},

{

"function": "wtype",

"label": \[

"wtype",

"摆动样式"

\],

"value": 0,

"data": \[

{

"label": \[

"Triangle",

"锯齿摆"

\],

"value": 0

},

{

"label": \[

"Sine",

"正弦摆"

\],

"value": 1

},

{

"label": \[

"Crescent",

"月牙摆"

\],

"value": 2

},

{

"label": \[

"Spatial Triangle",

"空间三角摆"

\],

"value": 3

}

\]

},

{

"function": "wfreq",

"label": \[

"wfreq",

"摆动频率"

\],

"value": 1,

"rule": {

"unit": "Hz",

"min": 0,

"max": 65535

}

},

{

"function": "wamp",

"label": \[

"wamp",

"摆动幅度"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "left",

"label": \[

"left",

"左停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "right",

"label": \[

"right",

"右停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "middle",

"label": \[

"middle",

"中间停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "wrotanglex",

"label": \[

"wrotanglex",

"操作角"

\],

"value": 0,

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

},

{

"function": "wrotanglez",

"label": \[

"wrotanglez",

"摆动角"

\],

"value": 0,

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

},

{

"function": "sagitta",

"label": \[

"sagitta",

"弦高"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "direction",

"label": \[

"direction",

"摆动方向"

\],

"value": 1,

"data": \[

{

"label": \[

"Positive Crescent",

"正月牙"

\],

"value": 1

},

{

"label": \[

"Negative Crescent",

"反月牙"

\],

"value": -1

}

\]

},

{

"function": "xOffset",

"label": \[

"xOffset",

"x偏移"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "yOffset",

"label": \[

"yOffset",

"y偏移"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "zOffset",

"label": \[

"zOffset",

"z偏移"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "aOffset",

"label": \[

"aOffset",

"a偏移"

\],

"value": 0,

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

}

\],

\[                            // 模板二焊缝四

{

"function": "speed",

"label": \[

"speed",

"速度"

\],

"value": 0,

"rule": {

"unit": "mm/s",

"min": -65535,

"max": 65535

}

},

{

"function": "wtype",

"label": \[

"wtype",

"摆动样式"

\],

"value": 0,

"data": \[

{

"label": \[

"Triangle",

"锯齿摆"

\],

"value": 0

},

{

"label": \[

"Sine",

"正弦摆"

\],

"value": 1

},

{

"label": \[

"Crescent",

"月牙摆"

\],

"value": 2

},

{

"label": \[

"Spatial Triangle",

"空间三角摆"

\],

"value": 3

}

\]

},

{

"function": "wfreq",

"label": \[

"wfreq",

"摆动频率"

\],

"value": 1,

"rule": {

"unit": "Hz",

"min": 0,

"max": 65535

}

},

{

"function": "wamp",

"label": \[

"wamp",

"摆动幅度"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "left",

"label": \[

"left",

"左停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "right",

"label": \[

"right",

"右停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "middle",

"label": \[

"middle",

"中间停留"

\],

"value": 0,

"rule": {

"unit": "ms",

"min": 0,

"max": 65535

}

},

{

"function": "wrotanglex",

"label": \[

"wrotanglex",

"操作角"

\],

"value": 0,

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

},

{

"function": "wrotanglez",

"label": \[

"wrotanglez",

"摆动角"

\],

"value": 0,

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

},

{

"function": "sagitta",

"label": \[

"sagitta",

"弦高"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "direction",

"label": \[

"direction",

"摆动方向"

\],

"value": 1,

"data": \[

{

"label": \[

"Positive Crescent",

"正月牙"

\],

"value": 1

},

{

"label": \[

"Negative Crescent",

"反月牙"

\],

"value": -1

}

\]

},

{

"function": "xOffset",

"label": \[

"xOffset",

"x偏移"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "yOffset",

"label": \[

"yOffset",

"y偏移"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "zOffset",

"label": \[

"zOffset",

"z偏移"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "aOffset",

"label": \[

"aOffset",

"a偏移"

\],

"value": 0,

"rule": {

"unit": "deg",

"min": -65535,

"max": 65535

}

}

\]

\]

}

}

\]

}
```


**响应数据**:

```json
{

"id":1,

"ty":"welder/setMultiWeld",

"db": ""

}
```


### 23.14获取寻位工艺模板

**接口类型:** welder/getSearchTemplateList

返回一个寻位工艺模板json

**请求数据**:

```json
{

"id":1,

"ty":"welder/getSearchTemplateList",

"db":""

}
```


**响应数据**:

```json
{

"id": 1,

"ty": "welder/getSearchTemplateList",

"db": \[                                // 寻位模板数组

{

"tmpname": "Template Name",    // 寻位模板名称

"id": 1,                       // 寻位ID

"params": \[

{

"function": "speed",

"label": \[

"speed",

"寻位速度"

\],

"value": 0,            // 寻位速度

"rule": {

"unit": "mm/s",

"min": -65535,

"max": 65535

}

},

{

"function": "masterFlag",

"label": \[

"masterFlag",

"旗标"

\],

"value": 0,            // 寻位旗标 0：关闭 1：打开

"data": \[

{

"label": \[

"close",

"关闭"

\],

"value": 0

},

{

"label": \[

"open",

"打开"

\],

"value": 1

}

\]

},

{

"function": "searchCrood",

"label": \[

"searchCrood",

"寻位坐标系"

\],

"value": 0,    // 寻位旗标 0~15 坐标系0~坐标系15

"data": \[

{

"label": \[

"Coordinate System 0",

"坐标系0"

\],

"value": 0

},

{

"label": \[

"Coordinate System 1",

"坐标系1"

\],

"value": 1

},

{

"label": \[

"Coordinate System 2",

"坐标系2"

\],

"value": 2

},

{

"label": \[

"Coordinate System 3",

"坐标系3"

\],

"value": 3

},

{

"label": \[

"Coordinate System 4",

"坐标系4"

\],

"value": 4

},

{

"label": \[

"Coordinate System 5",

"坐标系5"

\],

"value": 5

},

{

"label": \[

"Coordinate System 6",

"坐标系6"

\],

"value": 6

},

{

"label": \[

"Coordinate System 7",

"坐标系7"

\],

"value": 7

},

{

"label": \[

"Coordinate System 8",

"坐标系8"

\],

"value": 8

},

{

"label": \[

"Coordinate System 9",

"坐标系9"

\],

"value": 9

},

{

"label": \[

"Coordinate System 10",

"坐标系10"

\],

"value": 10

},

{

"label": \[

"Coordinate System 11",

"坐标系11"

\],

"value": 11

},

{

"label": \[

"Coordinate System 12",

"坐标系12"

\],

"value": 12

},

{

"label": \[

"Coordinate System 13",

"坐标系13"

\],

"value": 13

},

{

"label": \[

"Coordinate System 14",

"坐标系14"

\],

"value": 14

},

{

"label": \[

"Coordinate System 15",

"坐标系15"

\],

"value": 15

}

\]

},

{

"function": "seamType",

"label": \[

"seamType",

"焊缝类型"

\],

"value": 0,        // 焊缝类型 0：角焊缝 1：V坡 2：内外径

"data": \[

{

"label": \[

"filletWeld",

"角焊缝"

\],

"value": 0

},

{

"label": \[

"v-Prep",

"V坡"

\],

"value": 1

},

{

"label": \[

"ID/OD",

"内外径"

\],

"value": 2

}

\]

},

{

"function": "searchMode",

"label": \[

"searchMode",

"寻位模式"

\],

"value": 0, // 寻位模式 0：1D平移 1：2D平移 2：3D平移 4：2D旋转
     5：3D旋转

"data": \[

{

"label": \[

"1D-Trans",

"1D平移"

\],

"value": 0

},

{

"label": \[

"2D-Trans",

"2D平移"

\],

"value": 1

},

{

"label": \[

"3D-Trans",

"3D平移"

\],

"value": 2

},

{

"label": \[

"2D-Rot",

"2D旋转"

\],

"value": 4

},

{

"label": \[

"3D-Rot",

"3D旋转"

\],

"value": 5

}

\]

},

{

"function": "maxRange",

"label": \[

"maxRange",

"寻位最大距离"

\],

"value": 0,            //寻位最大距离 单位：mm

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "incrementalSearch",

"label": \[

"incrementalSearch",

"增量寻位"

\],

"value": 0,        // 增量寻位 0：关闭 1：打开

"data": \[

{

"label": \[

"close",

"关闭"

\],

"value": 0

},

{

"label": \[

"open",

"打开"

\],

"value": 1

}

\]

},

{

"function": "autoReturn",

"label": \[

"autoReturn",

"自动返回"

\],

"value": 0,    // 自动返回 0：关闭 1：开启

"data": \[

{

"label": \[

"close",

"关闭"

\],

"value": 0

},

{

"label": \[

"open",

"打开"

\],

"value": 1

}

\]

}

\]

},

{

"tmpname": "Template Name",

"id": 2,

"params": \[

{

"function": "speed",

"label": \[

"speed",

"寻位速度"

\],

"value": 0,

"rule": {

"unit": "mm/s",

"min": -65535,

"max": 65535

}

},

{

"function": "masterFlag",

"label": \[

"masterFlag",

"旗标"

\],

"value": 0,

"data": \[

{

"label": \[

"close",

"关闭"

\],

"value": 0

},

{

"label": \[

"open",

"打开"

\],

"value": 1

}

\]

},

{

"function": "searchCrood",

"label": \[

"searchCrood",

"寻位坐标系"

\],

"value": 0,

"data": \[

{

"label": \[

"Coordinate System 0",

"坐标系0"

\],

"value": 0

},

{

"label": \[

"Coordinate System 1",

"坐标系1"

\],

"value": 1

},

{

"label": \[

"Coordinate System 2",

"坐标系2"

\],

"value": 2

},

{

"label": \[

"Coordinate System 3",

"坐标系3"

\],

"value": 3

},

{

"label": \[

"Coordinate System 4",

"坐标系4"

\],

"value": 4

},

{

"label": \[

"Coordinate System 5",

"坐标系5"

\],

"value": 5

},

{

"label": \[

"Coordinate System 6",

"坐标系6"

\],

"value": 6

},

{

"label": \[

"Coordinate System 7",

"坐标系7"

\],

"value": 7

},

{

"label": \[

"Coordinate System 8",

"坐标系8"

\],

"value": 8

},

{

"label": \[

"Coordinate System 9",

"坐标系9"

\],

"value": 9

},

{

"label": \[

"Coordinate System 10",

"坐标系10"

\],

"value": 10

},

{

"label": \[

"Coordinate System 11",

"坐标系11"

\],

"value": 11

},

{

"label": \[

"Coordinate System 12",

"坐标系12"

\],

"value": 12

},

{

"label": \[

"Coordinate System 13",

"坐标系13"

\],

"value": 13

},

{

"label": \[

"Coordinate System 14",

"坐标系14"

\],

"value": 14

},

{

"label": \[

"Coordinate System 15",

"坐标系15"

\],

"value": 15

}

\]

},

{

"function": "seamType",

"label": \[

"seamType",

"焊缝类型"

\],

"value": 0,

"data": \[

{

"label": \[

"filletWeld",

"角焊缝"

\],

"value": 0

},

{

"label": \[

"v-Prep",

"V坡"

\],

"value": 1

},

{

"label": \[

"ID/OD",

"内外径"

\],

"value": 2

}

\]

},

{

"function": "searchMode",

"label": \[

"searchMode",

"寻位模式"

\],

"value": 0,

"data": \[

{

"label": \[

"1D-Trans",

"1D平移"

\],

"value": 0

},

{

"label": \[

"2D-Trans",

"2D平移"

\],

"value": 1

},

{

"label": \[

"3D-Trans",

"3D平移"

\],

"value": 2

},

{

"label": \[

"2D-Rot",

"2D旋转"

\],

"value": 4

},

{

"label": \[

"3D-Rot",

"3D旋转"

\],

"value": 5

}

\]

},

{

"function": "maxRange",

"label": \[

"maxRange",

"寻位最大距离"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "incrementalSearch",

"label": \[

"incrementalSearch",

"增量寻位"

\],

"value": 0,

"data": \[

{

"label": \[

"close",

"关闭"

\],

"value": 0

},

{

"label": \[

"open",

"打开"

\],

"value": 1

}

\]

},

{

"function": "autoReturn",

"label": \[

"autoReturn",

"自动返回"

\],

"value": 0,

"data": \[

{

"label": \[

"close",

"关闭"

\],

"value": 0

},

{

"label": \[

"open",

"打开"

\],

"value": 1

}

\]

}

\]

}

\]

}
```


### 23.15 保存寻位工艺模板

**接口类型:** welder/setSearch

寻位工艺模板为数组，如需保存多个，添加多个模板对象到数组中

**请求数据**:

```json
{   

"id": 1,

"ty": "welder/setSearch",

"db": \[

{

"tmpname": "Template Name",

"id": 1,

"params": \[

{

"function": "speed",

"label": \[

"speed",

"寻位速度"

\],

"value": 0,

"rule": {

"unit": "mm/s",

"min": -65535,

"max": 65535

}

},

{

"function": "masterFlag",

"label": \[

"masterFlag",

"旗标"

\],

"value": 0,

"data": \[

{

"label": \[

"close",

"关闭"

\],

"value": 0

},

{

"label": \[

"open",

"打开"

\],

"value": 1

}

\]

},

{

"function": "searchCrood",

"label": \[

"searchCrood",

"寻位坐标系"

\],

"value": 0,

"data": \[

{

"label": \[

"Coordinate System 0",

"坐标系0"

\],

"value": 0

},

{

"label": \[

"Coordinate System 1",

"坐标系1"

\],

"value": 1

},

{

"label": \[

"Coordinate System 2",

"坐标系2"

\],

"value": 2

},

{

"label": \[

"Coordinate System 3",

"坐标系3"

\],

"value": 3

},

{

"label": \[

"Coordinate System 4",

"坐标系4"

\],

"value": 4

},

{

"label": \[

"Coordinate System 5",

"坐标系5"

\],

"value": 5

},

{

"label": \[

"Coordinate System 6",

"坐标系6"

\],

"value": 6

},

{

"label": \[

"Coordinate System 7",

"坐标系7"

\],

"value": 7

},

{

"label": \[

"Coordinate System 8",

"坐标系8"

\],

"value": 8

},

{

"label": \[

"Coordinate System 9",

"坐标系9"

\],

"value": 9

},

{

"label": \[

"Coordinate System 10",

"坐标系10"

\],

"value": 10

},

{

"label": \[

"Coordinate System 11",

"坐标系11"

\],

"value": 11

},

{

"label": \[

"Coordinate System 12",

"坐标系12"

\],

"value": 12

},

{

"label": \[

"Coordinate System 13",

"坐标系13"

\],

"value": 13

},

{

"label": \[

"Coordinate System 14",

"坐标系14"

\],

"value": 14

},

{

"label": \[

"Coordinate System 15",

"坐标系15"

\],

"value": 15

}

\]

},

{

"function": "seamType",

"label": \[

"seamType",

"焊缝类型"

\],

"value": 0,

"data": \[

{

"label": \[

"filletWeld",

"角焊缝"

\],

"value": 0

},

{

"label": \[

"v-Prep",

"V坡"

\],

"value": 1

},

{

"label": \[

"ID/OD",

"内外径"

\],

"value": 2

}

\]

},

{

"function": "searchMode",

"label": \[

"searchMode",

"寻位模式"

\],

"value": 0,

"data": \[

{

"label": \[

"1D-Trans",

"1D平移"

\],

"value": 0

},

{

"label": \[

"2D-Trans",

"2D平移"

\],

"value": 1

},

{

"label": \[

"3D-Trans",

"3D平移"

\],

"value": 2

},

{

"label": \[

"2D-Rot",

"2D旋转"

\],

"value": 4

},

{

"label": \[

"3D-Rot",

"3D旋转"

\],

"value": 5

}

\]

},

{

"function": "maxRange",

"label": \[

"maxRange",

"寻位最大距离"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "incrementalSearch",

"label": \[

"incrementalSearch",

"增量寻位"

\],

"value": 0,

"data": \[

{

"label": \[

"close",

"关闭"

\],

"value": 0

},

{

"label": \[

"open",

"打开"

\],

"value": 1

}

\]

},

{

"function": "autoReturn",

"label": \[

"autoReturn",

"自动返回"

\],

"value": 0,

"data": \[

{

"label": \[

"close",

"关闭"

\],

"value": 0

},

{

"label": \[

"open",

"打开"

\],

"value": 1

}

\]

}

\]

},

{

"tmpname": "Template Name",

"id": 2,

"params": \[

{

"function": "speed",

"label": \[

"speed",

"寻位速度"

\],

"value": 0,

"rule": {

"unit": "mm/s",

"min": -65535,

"max": 65535

}

},

{

"function": "masterFlag",

"label": \[

"masterFlag",

"旗标"

\],

"value": 0,

"data": \[

{

"label": \[

"close",

"关闭"

\],

"value": 0

},

{

"label": \[

"open",

"打开"

\],

"value": 1

}

\]

},

{

"function": "searchCrood",

"label": \[

"searchCrood",

"寻位坐标系"

\],

"value": 0,

"data": \[

{

"label": \[

"Coordinate System 0",

"坐标系0"

\],

"value": 0

},

{

"label": \[

"Coordinate System 1",

"坐标系1"

\],

"value": 1

},

{

"label": \[

"Coordinate System 2",

"坐标系2"

\],

"value": 2

},

{

"label": \[

"Coordinate System 3",

"坐标系3"

\],

"value": 3

},

{

"label": \[

"Coordinate System 4",

"坐标系4"

\],

"value": 4

},

{

"label": \[

"Coordinate System 5",

"坐标系5"

\],

"value": 5

},

{

"label": \[

"Coordinate System 6",

"坐标系6"

\],

"value": 6

},

{

"label": \[

"Coordinate System 7",

"坐标系7"

\],

"value": 7

},

{

"label": \[

"Coordinate System 8",

"坐标系8"

\],

"value": 8

},

{

"label": \[

"Coordinate System 9",

"坐标系9"

\],

"value": 9

},

{

"label": \[

"Coordinate System 10",

"坐标系10"

\],

"value": 10

},

{

"label": \[

"Coordinate System 11",

"坐标系11"

\],

"value": 11

},

{

"label": \[

"Coordinate System 12",

"坐标系12"

\],

"value": 12

},

{

"label": \[

"Coordinate System 13",

"坐标系13"

\],

"value": 13

},

{

"label": \[

"Coordinate System 14",

"坐标系14"

\],

"value": 14

},

{

"label": \[

"Coordinate System 15",

"坐标系15"

\],

"value": 15

}

\]

},

{

"function": "seamType",

"label": \[

"seamType",

"焊缝类型"

\],

"value": 0,

"data": \[

{

"label": \[

"filletWeld",

"角焊缝"

\],

"value": 0

},

{

"label": \[

"v-Prep",

"V坡"

\],

"value": 1

},

{

"label": \[

"ID/OD",

"内外径"

\],

"value": 2

}

\]

},

{

"function": "searchMode",

"label": \[

"searchMode",

"寻位模式"

\],

"value": 0,

"data": \[

{

"label": \[

"1D-Trans",

"1D平移"

\],

"value": 0

},

{

"label": \[

"2D-Trans",

"2D平移"

\],

"value": 1

},

{

"label": \[

"3D-Trans",

"3D平移"

\],

"value": 2

},

{

"label": \[

"2D-Rot",

"2D旋转"

\],

"value": 4

},

{

"label": \[

"3D-Rot",

"3D旋转"

\],

"value": 5

}

\]

},

{

"function": "maxRange",

"label": \[

"maxRange",

"寻位最大距离"

\],

"value": 0,

"rule": {

"unit": "mm",

"min": -65535,

"max": 65535

}

},

{

"function": "incrementalSearch",

"label": \[

"incrementalSearch",

"增量寻位"

\],

"value": 0,

"data": \[

{

"label": \[

"close",

"关闭"

\],

"value": 0

},

{

"label": \[

"open",

"打开"

\],

"value": 1

}

\]

},

{

"function": "autoReturn",

"label": \[

"autoReturn",

"自动返回"

\],

"value": 0,

"data": \[

{

"label": \[

"close",

"关闭"

\],

"value": 0

},

{

"label": \[

"open",

"打开"

\],

"value": 1

}

\]

}

\]

}

\]

}
```


**响应数据**:

```json
{

"id":1,

"ty":"welder/setSearch",

"db": ""

}
```


### 23.16 实时调节

**接口类型:** welder/sendparams

**请求数据**:

```json
{

"id":1,

"ty":"welder/sendparams",

"db":{

"adjCurrent": 3, // 调整电流值

"adjVoltage": 0, // 调整电压值

"incCurrent": 1, // 增量

"incVoltage": 1 // 增量

}

}
```


**响应数据**:

```json
{

"id":1,

"ty":"welder/sendparams",

"db":null

}
```


### 23.17 获取实时调节

**接口类型:** welder/sendparams

**请求数据**:

```json
{

"id":1,

"ty":"welder/getRtParamAdjust",

"db":""

}
```


**响应数据**:

```json
{

"id":1,

"ty":"welder/getRtParamAdjust",

"db":{

"actCurrent": 0, // 实际电流

"actVoltage": 0, // 实际电压

"adjCurrent": 3, // 原始电流

"adjVoltage": 0, // 原始电压

"incCurrent": 1, // 增量

"incVoltage": 1 // 增量

}

}
```
