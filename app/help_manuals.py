"""各功能页帮助手册 HTML 内容（中/英）。"""

from __future__ import annotations

from app.i18n import I18nManager


def welding_manual_html() -> str:
  lang = I18nManager.instance().lang
  if lang == "en":
    return _WELDING_EN
  return _WELDING_ZH


def upload_manual_html() -> str:
  lang = I18nManager.instance().lang
  if lang == "en":
    return _UPLOAD_EN
  return _UPLOAD_ZH


_WELDING_ZH = """
<h1>焊接界面帮助</h1>
<p>焊接页用于将文字排版为焊接轨迹，生成 Lua 程序与点位文件，供上传页部署到机器人。</p>

<h2>1. 焊机操作（顶部横条）</h2>
<ul>
  <li><b>送气 / 送丝 / 退丝</b>：按住按钮生效，松开即停止（需已连接机器人）。</li>
</ul>

<h2>2. 焊接文字</h2>
<ul>
  <li>在文本框输入要焊接的内容，支持多行（Enter 换行）。</li>
  <li><b>生成模式</b>：
    <ul>
      <li><b>轮廓字</b>：TTF 字体填充轮廓，适合实心字焊接。</li>
      <li><b>骨架数字字母</b>：Hershey 单线字，适合英文与数字。</li>
      <li><b>骨架汉字</b>：MakeMeAHanzi 笔画数据，适合中文。</li>
    </ul>
  </li>
  <li><b>字体</b>：随模式变化；轮廓字从预设 TTF 中选择，骨架模式使用对应字库。</li>
</ul>

<h2>3. 排版参数</h2>
<ul>
  <li><b>字高 / 字间距 / 行间距 / 边距</b>：控制文字在工作平面内的尺寸与位置。</li>
  <li>标有 <code>[Beta]</code> 的选项（排版方向、对齐、流向等）为实验功能，正式焊接建议保持默认。</li>
</ul>

<h2>4. 工作空间标定</h2>
<p>用三个角点（左上、右上、左下）定义文字焊接平面：</p>
<ol>
  <li>将机器人 TCP 移到角点位置。</li>
  <li>点击该行的 <b>更新</b>，从当前位姿读入坐标（需 CRI/UDP 位姿有效）。</li>
  <li>可用 <b>移动至</b> 让机器人走到已填坐标（按住运动，松开停止）。</li>
  <li><b>复制</b> 将当前行坐标复制到剪贴板。</li>
</ol>
<p class="note">标定准确与否直接影响生成轨迹在工件上的位置。</p>

<h2>5. 焊接与工艺参数</h2>
<ul>
  <li><b>引入 / 引出 / 搭接 / 点距</b>：路径几何与采样密度。</li>
  <li><b>工艺参数</b>：电压、电流、焊接速度、空走速度、任务号、电感等，写入生成的 Lua。</li>
  <li><b>工作空间 Z</b>：焊接高度、空移安全高度、超安全高度增量。</li>
  <li><b>Lua 运动参数</b>：加速度、过渡模式（absolute/relative）、可选 wait 插入。</li>
</ul>

<h2>6. 右侧操作</h2>
<ul>
  <li><b>生成焊接点</b>：离线计算轨迹，输出到 <code>output/</code> 目录（含 <code>.lua</code>、<code>.txt</code>、预览图等）。</li>
  <li><b>预览</b>：打开最近一次生成的 2D 预览图。</li>
  <li><b>导出 TXT</b>：打开或定位导出的点位文本。</li>
</ul>
<p>下方 <b>输出日志</b> 显示生成过程与错误信息。</p>

<h2>7. 典型流程</h2>
<ol>
  <li>连接机器人 → 标定工作空间三点 → 输入文字并设置参数。</li>
  <li>点击「生成焊接点」→ 检查日志与预览。</li>
  <li>切换到 <b>上传</b> 页，将生成的 <code>.lua</code> 上传并绑定槽位。</li>
</ol>
<p class="warn">左侧运动抽屉可在任意页面点动机器人；切页时自动停止点动。</p>
<p class="note">参数修改会自动保存，下次进入焊接页时恢复。</p>
"""

_WELDING_EN = """
<h1>Welding Page Help</h1>
<p>The Welding page layouts text into weld trajectories and generates Lua programs and point files for the Upload page.</p>

<h2>1. Welder Controls (top bar)</h2>
<ul>
  <li><b>Gas / Wire feed / Wire retract</b>: hold to activate, release to stop (robot must be connected).</li>
</ul>

<h2>2. Weld Text</h2>
<ul>
  <li>Enter text in the editor; multi-line input is supported.</li>
  <li><b>Generate mode</b>:
    <ul>
      <li><b>Contour</b>: TTF filled outlines for solid characters.</li>
      <li><b>Latin stroke</b>: Hershey single-line font for letters and digits.</li>
      <li><b>Hanzi stroke</b>: MakeMeAHanzi stroke data for Chinese.</li>
    </ul>
  </li>
  <li><b>Font</b>: depends on mode; contour uses TTF presets, stroke modes use their own glyph sources.</li>
</ul>

<h2>3. Layout</h2>
<ul>
  <li><b>Char height / spacing / margins</b>: size and placement on the work plane.</li>
  <li>Options marked <code>[Beta]</code> (direction, alignment, flow) are experimental; keep defaults for production welds.</li>
</ul>

<h2>4. Workspace Calibration</h2>
<p>Three corners (left-top, right-top, left-bottom) define the text plane:</p>
<ol>
  <li>Move the TCP to each corner.</li>
  <li>Click <b>Update</b> to read the current pose (valid CRI/UDP pose required).</li>
  <li><b>Move To</b> drives the robot to the entered pose (hold to move, release to stop).</li>
  <li><b>Copy</b> copies the row to the clipboard.</li>
</ol>

<h2>5. Weld &amp; Process Parameters</h2>
<ul>
  <li><b>Lead-in / lead-out / overlap / point spacing</b>: path geometry and sampling.</li>
  <li><b>Process params</b>: voltage, current, weld/travel speed, job number, inductance — written into Lua.</li>
  <li><b>Workspace Z</b>: weld height, safe travel height, super-safe extra offset.</li>
  <li><b>Lua motion</b>: acceleration, blend mode (absolute/relative), optional wait insertion.</li>
</ul>

<h2>6. Right Panel</h2>
<ul>
  <li><b>Generate Weld Points</b>: offline pipeline → <code>output/</code> (<code>.lua</code>, <code>.txt</code>, preview image, etc.).</li>
  <li><b>Preview</b>: open the latest 2D preview image.</li>
  <li><b>Export TXT</b>: open or locate the exported point file.</li>
</ul>
<p>The <b>Output Log</b> shows progress and errors.</p>

<h2>7. Typical Workflow</h2>
<ol>
  <li>Connect → calibrate three workspace corners → enter text and parameters.</li>
  <li>Generate → verify log and preview.</li>
  <li>Switch to <b>Upload</b> and deploy the <code>.lua</code> with slot binding.</li>
</ol>
<p class="warn">The left motion drawer jogs the robot on any page; jogging stops when you change tabs.</p>
<p class="note">Settings are saved automatically when you edit them.</p>
"""

_UPLOAD_ZH = """
<h1>上传界面帮助</h1>
<p>上传页将焊接页生成的 Lua 工程部署到机器人控制器，并管理工程与槽位（Map Index）的绑定关系。</p>
<p class="warn">使用前须已在登录页连接机器人；未连接时所有操作按钮不可用。</p>

<h2>1. 上传 Lua 工程</h2>
<ul>
  <li><b>Lua 文件</b>：选择 <code>.lua</code> 路径。
    <ul>
      <li><b>浏览</b>：从磁盘选择文件。</li>
      <li><b>最新输出</b>：自动选取 <code>output/</code> 下最近修改的 <code>.lua</code>。</li>
    </ul>
  </li>
  <li><b>工程名</b>：控制器上显示的名称；若留空且选了文件，会用文件名（不含扩展名）填充。</li>
  <li><b>上传方式</b>：
    <ul>
      <li><b>仅上传</b>：在服务器新建或覆盖工程，不修改槽位绑定。</li>
      <li><b>上传并绑定槽位</b>：上传成功后，将工程绑定到指定槽位（0–127）。</li>
    </ul>
  </li>
  <li><b>上传到服务器</b>：后台执行，期间界面会暂时禁用相关按钮。</li>
</ul>

<h2>2. 工程名冲突</h2>
<p>若服务器已存在同名工程，会提示：</p>
<ul>
  <li><b>覆盖</b>：用新 Lua 替换原工程内容。</li>
  <li><b>重命名</b>：输入新名称后再次上传。</li>
  <li><b>取消</b>：放弃本次上传。</li>
</ul>

<h2>3. 槽位绑定</h2>
<ul>
  <li><b>刷新列表</b>：从机器人读取工程列表与槽位映射（进入本页且已连接时也会自动刷新）。</li>
  <li><b>选择工程</b> + <b>槽位</b> + <b>绑定到槽位</b>：将已有工程绑定到指定槽位，无需重新上传 Lua。</li>
  <li><b>当前工程绑定</b>：显示所选工程已占用的槽位号。</li>
  <li><b>槽位映射（只读）</b>：列出当前所有已占用槽位及对应工程名。</li>
</ul>
<p class="note">槽位用于控制器侧选择要运行的 Lua 工程；具体调用方式取决于机器人程序配置。</p>

<h2>4. 上传日志</h2>
<p>右侧面板实时显示上传、刷新、绑定结果与错误信息。</p>

<h2>5. 典型流程</h2>
<ol>
  <li>在焊接页生成轨迹，得到 <code>output/…/*.lua</code>。</li>
  <li>进入上传页 →「最新输出」或浏览选择 Lua → 填写工程名。</li>
  <li>选择「上传并绑定槽位」，指定槽位（如 0）→ 上传。</li>
  <li>在机器人端通过对应槽位或工程名运行焊接程序。</li>
</ol>
<p class="note">路径、工程名、上传方式与槽位会保存，下次打开时恢复。</p>
"""

_UPLOAD_EN = """
<h1>Upload Page Help</h1>
<p>The Upload page deploys Lua projects generated on the Welding page to the robot controller and manages project-to-slot (map index) bindings.</p>
<p class="warn">Connect on the login page first; controls are disabled when disconnected.</p>

<h2>1. Upload Lua Project</h2>
<ul>
  <li><b>Lua file</b>: path to the <code>.lua</code> file.
    <ul>
      <li><b>Browse</b>: pick from disk.</li>
      <li><b>Latest Output</b>: newest <code>.lua</code> under <code>output/</code> by modification time.</li>
    </ul>
  </li>
  <li><b>Project name</b>: display name on the server; if empty, the file stem may be used.</li>
  <li><b>Upload mode</b>:
    <ul>
      <li><b>Upload only</b>: create or overwrite on the server without changing slot bindings.</li>
      <li><b>Upload and bind slot</b>: after upload, bind the project to slot 0–127.</li>
    </ul>
  </li>
  <li><b>Upload to Server</b>: runs in the background; UI controls are briefly disabled.</li>
</ul>

<h2>2. Duplicate Project Name</h2>
<p>If the name already exists on the server:</p>
<ul>
  <li><b>Overwrite</b>: replace the existing project Lua.</li>
  <li><b>Rename</b>: enter a new name and upload again.</li>
  <li><b>Cancel</b>: abort.</li>
</ul>

<h2>3. Slot Binding</h2>
<ul>
  <li><b>Refresh List</b>: fetch projects and slot map from the robot (also on page enter when connected).</li>
  <li><b>Select project</b> + <b>slot</b> + <b>Bind to Slot</b>: bind an existing project without re-uploading Lua.</li>
  <li><b>Current binding</b>: slots already used by the selected project.</li>
  <li><b>Slot map (read-only)</b>: all occupied slots and project names.</li>
</ul>

<h2>4. Upload Log</h2>
<p>The right panel shows upload, refresh, bind results, and errors.</p>

<h2>5. Typical Workflow</h2>
<ol>
  <li>Generate on the Welding page → <code>output/…/*.lua</code>.</li>
  <li>Open Upload → Latest Output or Browse → enter project name.</li>
  <li>Choose Upload and bind slot, set slot (e.g. 0) → upload.</li>
  <li>Run the weld program on the robot via the bound slot or project name.</li>
</ol>
<p class="note">Paths, names, modes, and slots are persisted across sessions.</p>
"""
