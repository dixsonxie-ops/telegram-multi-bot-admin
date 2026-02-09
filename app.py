from flask import Flask, request, jsonify
import sqlite3
import os

app = Flask(__name__)

# Railway 持久化磁盘建议挂载到 /app/data
DATA_DIR = os.environ.get("DATA_DIR", "data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_FILE = os.path.join(DATA_DIR, "bot.db")

def get_db():
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_db_if_needed():
    conn = get_db()
    cur = conn.cursor()

    # bots
    cur.execute("""
    CREATE TABLE IF NOT EXISTS bots (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      token TEXT NOT NULL,
      enabled INTEGER NOT NULL DEFAULT 1
    )
    """)

    # rules
    cur.execute("""
    CREATE TABLE IF NOT EXISTS rules (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      bot_id INTEGER NOT NULL,
      action_type TEXT DEFAULT 'edit_send',
      source_group_id TEXT NOT NULL,
      target_group_id TEXT NOT NULL,
      user_id TEXT DEFAULT '',
      user_ids TEXT DEFAULT '',
      keyword TEXT NOT NULL,
      enabled INTEGER NOT NULL DEFAULT 1,
      append_text TEXT DEFAULT '',
      merchant_regex TEXT DEFAULT '',
      lookup_url TEXT DEFAULT '',
      replace_template TEXT DEFAULT '',
      reply_text TEXT DEFAULT ''
    )
    """)

    # logs
    cur.execute("""
    CREATE TABLE IF NOT EXISTS logs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts TEXT NOT NULL,
      bot_id INTEGER,
      rule_id INTEGER,
      message_type TEXT,
      message_text TEXT
    )
    """)

    # status
    cur.execute("""
    CREATE TABLE IF NOT EXISTS status (
      bot_id INTEGER NOT NULL,
      key TEXT NOT NULL,
      value TEXT DEFAULT '',
      PRIMARY KEY (bot_id, key)
    )
    """)

    # tg_users
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tg_users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id TEXT UNIQUE NOT NULL,
      name TEXT NOT NULL DEFAULT ''
    )
    """)

    # tg_groups
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tg_groups (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      group_id TEXT UNIQUE NOT NULL,
      name TEXT NOT NULL DEFAULT ''
    )
    """)

    conn.commit()
    conn.close()

def get_last_seen(bot_id: int) -> str:
    conn = get_db()
    row = conn.execute(
        "SELECT value FROM status WHERE bot_id=? AND key='bot_last_seen'",
        (bot_id,)
    ).fetchone()
    conn.close()
    return row["value"] if row and row["value"] else ""

def action_cn(action_type: str) -> str:
    if action_type == "edit_send":
        return "功能1：编辑后发送"
    if action_type == "lookup_replace":
        return "功能2：查询替换发送"
    if action_type == "auto_reply":
        return "功能3：自动回复"
    return action_type or ""

@app.route("/")
def home():
    return """
    <h2>🤖 多机器人管理后台</h2>
    <p>
      <a href="/bots">🔑 机器人管理（Token）</a> |
      <a href="/rules">📌 规则管理</a> |
      <a href="/users">👤 用户ID 管理</a> |
      <a href="/groups">👥 群ID 管理</a> |
      <a href="/logs">📜 日志</a>
    </p>
    <hr>
    <p>提示：后台只负责配置；真正监听 Telegram 需要运行 <b>bot_runner.py</b>。</p>
    """

# -------------------- Bots --------------------
@app.route("/bots")
def bots_page():
    conn = get_db()
    bots = conn.execute("SELECT * FROM bots ORDER BY id DESC").fetchall()
    conn.close()

    rows = ""
    for b in bots:
        last_seen = get_last_seen(int(b["id"]))
        status_text = f"✅ 心跳: {last_seen}" if last_seen else "⚠️ 暂无心跳"
        rows += f"""
        <tr>
          <td>{b['id']}</td>
          <td>{b['name']}</td>
          <td>{"启用" if b['enabled'] else "禁用"}</td>
          <td>{status_text}</td>
          <td>
            <a href="/edit_bot/{b['id']}">编辑</a> |
            <a href="/toggle_bot/{b['id']}">切换启用/禁用</a> |
            <a href="/delete_bot/{b['id']}" onclick="return confirm('确定删除这个机器人吗？')">删除</a>
          </td>
        </tr>
        """

    return f"""
    <h2>🔑 机器人管理（Token）</h2>
    <p>
      <a href="/">⬅️ 返回</a> |
      <a href="/rules">📌 规则管理</a> |
      <a href="/users">👤 用户ID</a> |
      <a href="/groups">👥 群ID</a> |
      <a href="/logs">📜 日志</a>
    </p>
    <hr>

    <h3>新增机器人</h3>
    <form action="/add_bot" method="post">
      名称：<input name="name" placeholder="例如 机器人A"><br><br>
      Token：<input name="token" placeholder="从 BotFather 获取的 token" style="width:560px;"><br><br>
      状态：
      <select name="enabled">
        <option value="1">启用</option>
        <option value="0">禁用</option>
      </select><br><br>
      <button type="submit">新增</button>
    </form>

    <hr>
    <h3>机器人列表</h3>
    <table border="1" cellpadding="8">
      <tr><th>ID</th><th>名称</th><th>状态</th><th>在线心跳</th><th>操作</th></tr>
      {rows}
    </table>
    """

@app.route("/add_bot", methods=["POST"])
def add_bot():
    name = request.form.get("name", "").strip()
    token = request.form.get("token", "").strip()
    enabled = 1 if request.form.get("enabled") == "1" else 0
    if not name or not token:
        return "<script>alert('❌ 名称和Token必填');window.location.href='/bots';</script>"
    conn = get_db()
    conn.execute("INSERT INTO bots (name, token, enabled) VALUES (?, ?, ?)", (name, token, enabled))
    conn.commit()
    conn.close()
    return "<script>alert('✅ 新增机器人成功');window.location.href='/bots';</script>"

@app.route("/edit_bot/<int:bot_id>")
def edit_bot(bot_id):
    conn = get_db()
    b = conn.execute("SELECT * FROM bots WHERE id=?", (bot_id,)).fetchone()
    conn.close()
    if not b:
        return "<script>alert('❌ 机器人不存在');window.location.href='/bots';</script>"
    return f"""
    <h2>✏️ 编辑机器人 #{b['id']}</h2>
    <p><a href="/bots">⬅️ 返回机器人列表</a></p>
    <hr>
    <form action="/update_bot/{b['id']}" method="post">
      名称：<input name="name" value="{b['name']}"><br><br>
      Token：<input name="token" value="{b['token']}" style="width:560px;"><br><br>
      状态：
      <select name="enabled">
        <option value="1" {"selected" if b["enabled"] == 1 else ""}>启用</option>
        <option value="0" {"selected" if b["enabled"] == 0 else ""}>禁用</option>
      </select><br><br>
      <button type="submit">保存</button>
    </form>
    """

@app.route("/update_bot/<int:bot_id>", methods=["POST"])
def update_bot(bot_id):
    name = request.form.get("name", "").strip()
    token = request.form.get("token", "").strip()
    enabled = 1 if request.form.get("enabled") == "1" else 0
    if not name or not token:
        return "<script>alert('❌ 名称和Token必填');window.history.back();</script>"
    conn = get_db()
    conn.execute("UPDATE bots SET name=?, token=?, enabled=? WHERE id=?", (name, token, enabled, bot_id))
    conn.commit()
    conn.close()
    return "<script>alert('✅ 保存成功');window.location.href='/bots';</script>"

@app.route("/toggle_bot/<int:bot_id>")
def toggle_bot(bot_id):
    conn = get_db()
    b = conn.execute("SELECT enabled FROM bots WHERE id=?", (bot_id,)).fetchone()
    if b:
        new_status = 0 if b["enabled"] else 1
        conn.execute("UPDATE bots SET enabled=? WHERE id=?", (new_status, bot_id))
        conn.commit()
    conn.close()
    return "<script>alert('🔄 已切换');window.location.href='/bots';</script>"

@app.route("/delete_bot/<int:bot_id>")
def delete_bot(bot_id):
    conn = get_db()
    conn.execute("DELETE FROM bots WHERE id=?", (bot_id,))
    conn.execute("DELETE FROM rules WHERE bot_id=?", (bot_id,))
    conn.execute("DELETE FROM logs WHERE bot_id=?", (bot_id,))
    conn.execute("DELETE FROM status WHERE bot_id=?", (bot_id,))
    conn.commit()
    conn.close()
    return "<script>alert('🗑️ 已删除');window.location.href='/bots';</script>"


# -------------------- Users (tg_users) --------------------
@app.route("/users")
def users_page():
    conn = get_db()
    rows = conn.execute("SELECT * FROM tg_users ORDER BY id DESC").fetchall()
    conn.close()

    trs = ""
    for r in rows:
        trs += f"""
        <tr>
          <td>{r['id']}</td>
          <td>{r['user_id']}</td>
          <td>{r['name']}</td>
          <td>
            <a href="/edit_user/{r['id']}">编辑</a> |
            <a href="/delete_user/{r['id']}" onclick="return confirm('确定删除该用户ID吗？')">删除</a>
          </td>
        </tr>
        """

    return f"""
    <h2>👤 用户ID 管理</h2>
    <p><a href="/">⬅️ 返回</a> | <a href="/groups">👥 群ID 管理</a> | <a href="/rules">📌 规则管理</a></p>
    <hr>

    <h3>新增用户ID</h3>
    <form action="/add_user" method="post">
      用户ID：<input name="user_id" placeholder="例如 7796205169" style="width:320px;"><br><br>
      备注名：<input name="name" placeholder="例如 客服A / 运营小王" style="width:320px;"><br><br>
      <button type="submit">新增</button>
    </form>

    <hr>
    <h3>列表</h3>
    <table border="1" cellpadding="8">
      <tr><th>ID</th><th>用户ID</th><th>备注名</th><th>操作</th></tr>
      {trs}
    </table>
    """

@app.route("/add_user", methods=["POST"])
def add_user():
    user_id = (request.form.get("user_id") or "").strip()
    name = (request.form.get("name") or "").strip()
    if not user_id:
        return "<script>alert('❌ user_id 必填');window.location.href='/users';</script>"
    conn = get_db()
    try:
        conn.execute("INSERT INTO tg_users (user_id, name) VALUES (?, ?)", (user_id, name))
        conn.commit()
    except Exception as e:
        conn.close()
        return f"<script>alert('❌ 保存失败：{str(e).replace('\"','\\\"')}');window.location.href='/users';</script>"
    conn.close()
    return "<script>alert('✅ 新增成功');window.location.href='/users';</script>"

@app.route("/edit_user/<int:rid>")
def edit_user(rid):
    conn = get_db()
    r = conn.execute("SELECT * FROM tg_users WHERE id=?", (rid,)).fetchone()
    conn.close()
    if not r:
        return "<script>alert('❌ 不存在');window.location.href='/users';</script>"
    return f"""
    <h2>✏️ 编辑用户ID</h2>
    <p><a href="/users">⬅️ 返回</a></p>
    <hr>
    <form action="/update_user/{rid}" method="post">
      用户ID：<input name="user_id" value="{r['user_id']}" style="width:360px;"><br><br>
      备注名：<input name="name" value="{r['name']}" style="width:360px;"><br><br>
      <button type="submit">保存</button>
    </form>
    """

@app.route("/update_user/<int:rid>", methods=["POST"])
def update_user(rid):
    user_id = (request.form.get("user_id") or "").strip()
    name = (request.form.get("name") or "").strip()
    if not user_id:
        return "<script>alert('❌ user_id 必填');window.history.back();</script>"
    conn = get_db()
    try:
        conn.execute("UPDATE tg_users SET user_id=?, name=? WHERE id=?", (user_id, name, rid))
        conn.commit()
    except Exception as e:
        conn.close()
        return f"<script>alert('❌ 保存失败：{str(e).replace('\"','\\\"')}');window.history.back();</script>"
    conn.close()
    return "<script>alert('✅ 保存成功');window.location.href='/users';</script>"

@app.route("/delete_user/<int:rid>")
def delete_user(rid):
    conn = get_db()
    conn.execute("DELETE FROM tg_users WHERE id=?", (rid,))
    conn.commit()
    conn.close()
    return "<script>alert('🗑️ 已删除');window.location.href='/users';</script>"


# -------------------- Groups (tg_groups) --------------------
@app.route("/groups")
def groups_page():
    conn = get_db()
    rows = conn.execute("SELECT * FROM tg_groups ORDER BY id DESC").fetchall()
    conn.close()

    trs = ""
    for r in rows:
        trs += f"""
        <tr>
          <td>{r['id']}</td>
          <td>{r['group_id']}</td>
          <td>{r['name']}</td>
          <td>
            <a href="/edit_group/{r['id']}">编辑</a> |
            <a href="/delete_group/{r['id']}" onclick="return confirm('确定删除该群ID吗？')">删除</a>
          </td>
        </tr>
        """

    return f"""
    <h2>👥 群ID 管理</h2>
    <p><a href="/">⬅️ 返回</a> | <a href="/users">👤 用户ID 管理</a> | <a href="/rules">📌 规则管理</a></p>
    <hr>

    <h3>新增群ID</h3>
    <form action="/add_group" method="post">
      群ID：<input name="group_id" placeholder="-100..." style="width:420px;"><br><br>
      备注名：<input name="name" placeholder="例如 充值群 / 客服群 / 订单群" style="width:420px;"><br><br>
      <button type="submit">新增</button>
    </form>

    <hr>
    <h3>列表</h3>
    <table border="1" cellpadding="8">
      <tr><th>ID</th><th>群ID</th><th>备注名</th><th>操作</th></tr>
      {trs}
    </table>
    """

@app.route("/add_group", methods=["POST"])
def add_group():
    group_id = (request.form.get("group_id") or "").strip()
    name = (request.form.get("name") or "").strip()
    if not group_id:
        return "<script>alert('❌ group_id 必填');window.location.href='/groups';</script>"
    conn = get_db()
    try:
        conn.execute("INSERT INTO tg_groups (group_id, name) VALUES (?, ?)", (group_id, name))
        conn.commit()
    except Exception as e:
        conn.close()
        return f"<script>alert('❌ 保存失败：{str(e).replace('\"','\\\"')}');window.location.href='/groups';</script>"
    conn.close()
    return "<script>alert('✅ 新增成功');window.location.href='/groups';</script>"

@app.route("/edit_group/<int:rid>")
def edit_group(rid):
    conn = get_db()
    r = conn.execute("SELECT * FROM tg_groups WHERE id=?", (rid,)).fetchone()
    conn.close()
    if not r:
        return "<script>alert('❌ 不存在');window.location.href='/groups';</script>"
    return f"""
    <h2>✏️ 编辑群ID</h2>
    <p><a href="/groups">⬅️ 返回</a></p>
    <hr>
    <form action="/update_group/{rid}" method="post">
      群ID：<input name="group_id" value="{r['group_id']}" style="width:520px;"><br><br>
      备注名：<input name="name" value="{r['name']}" style="width:520px;"><br><br>
      <button type="submit">保存</button>
    </form>
    """

@app.route("/update_group/<int:rid>", methods=["POST"])
def update_group(rid):
    group_id = (request.form.get("group_id") or "").strip()
    name = (request.form.get("name") or "").strip()
    if not group_id:
        return "<script>alert('❌ group_id 必填');window.history.back();</script>"
    conn = get_db()
    try:
        conn.execute("UPDATE tg_groups SET group_id=?, name=? WHERE id=?", (group_id, name, rid))
        conn.commit()
    except Exception as e:
        conn.close()
        return f"<script>alert('❌ 保存失败：{str(e).replace('\"','\\\"')}');window.history.back();</script>"
    conn.close()
    return "<script>alert('✅ 保存成功');window.location.href='/groups';</script>"

@app.route("/delete_group/<int:rid>")
def delete_group(rid):
    conn = get_db()
    conn.execute("DELETE FROM tg_groups WHERE id=?", (rid,))
    conn.commit()
    conn.close()
    return "<script>alert('🗑️ 已删除');window.location.href='/groups';</script>"


# -------------------- Rules --------------------
@app.route("/rules")
def rules_page():
    conn = get_db()
    bots = conn.execute("SELECT id, name FROM bots ORDER BY id DESC").fetchall()
    rules = conn.execute("""
        SELECT r.*, b.name AS bot_name
        FROM rules r
        LEFT JOIN bots b ON b.id = r.bot_id
        ORDER BY r.id DESC
    """).fetchall()

    tg_users = conn.execute("SELECT * FROM tg_users ORDER BY id DESC").fetchall()
    tg_groups = conn.execute("SELECT * FROM tg_groups ORDER BY id DESC").fetchall()
    conn.close()

    user_map = {str(u["user_id"]): (u["name"] or "").strip() for u in tg_users}
    group_map = {str(g["group_id"]): (g["name"] or "").strip() for g in tg_groups}

    bot_options = "".join([f"<option value='{b['id']}'>{b['id']} - {b['name']}</option>" for b in bots])

    group_options = "".join([
        f"<option value='{g['group_id']}'>{(g['name'] or '').strip()} ({g['group_id']})</option>"
        for g in tg_groups
    ])
    user_options = "".join([
        f"<option value='{u['user_id']}'>{(u['name'] or '').strip()} ({u['user_id']})</option>"
        for u in tg_users
    ])

    rows = ""
    for r in rules:
        act = r["action_type"] or "edit_send"
        users_raw = (r["user_ids"] or r["user_id"] or "").strip()
        user_ids_list = [x.strip() for x in users_raw.replace("，", ",").split(",") if x.strip()]
        users_show = ", ".join([f"{user_map.get(uid)}({uid})" if user_map.get(uid) else uid for uid in user_ids_list])

        src = str(r["source_group_id"])
        tgt = str(r["target_group_id"])
        src_show = f"{group_map.get(src)} ({src})" if group_map.get(src) else src
        tgt_show = f"{group_map.get(tgt)} ({tgt})" if group_map.get(tgt) else tgt

        rows += f"""
        <tr>
          <td>{r['id']}</td>
          <td>{r['bot_id']} - {r['bot_name'] or ''}</td>
          <td>{action_cn(act)}</td>
          <td>{src_show}</td>
          <td>{tgt_show}</td>
          <td>{users_show}</td>
          <td>{r['keyword']}</td>
          <td>{"启用" if r['enabled'] else "禁用"}</td>
          <td>
            <a href="/edit_rule/{r['id']}">编辑</a> |
            <a href="/toggle_rule/{r['id']}">切换启用/禁用</a> |
            <a href="/delete_rule/{r['id']}" onclick="return confirm('确定删除规则吗？')">删除</a>
          </td>
        </tr>
        """

    html = """
    <h2>📌 规则管理</h2>
    <p>
      <a href="/">⬅️ 返回</a> |
      <a href="/bots">🔑 机器人管理</a> |
      <a href="/users">👤 用户ID</a> |
      <a href="/groups">👥 群ID</a> |
      <a href="/logs">📜 日志</a>
    </p>
    <hr>

    <h3>添加规则</h3>
    <p style="color:#555;">
      用户ID支持多个：用逗号分隔（例如 111,222,333）。<br>
      关键词支持多个：用逗号分隔。填 * 表示匹配任意消息。<br>
      功能3：自动在源群回复 reply_text（可多行）。<br>
      你可以在「用户ID/群ID」页面先维护备注名，然后这里下拉选择更清晰。
    </p>

    <form action="/add_rule" method="post">
      绑定机器人：<select name="bot_id">__BOT_OPTIONS__</select><br><br>

      动作类型：
      <select name="action_type">
        <option value="edit_send">功能1：编辑后发送</option>
        <option value="lookup_replace">功能2：查询替换发送</option>
        <option value="auto_reply">功能3：自动回复</option>
      </select><br><br>

      源群（可选下拉）：
      <select id="src_sel">
        <option value="">-- 选择群 --</option>
        __GROUP_OPTIONS__
      </select>
      <button type="button" onclick="pickSrc()">使用</button>
      <br><br>
      源群ID：<input id="source_group_id" name="source_group_id" placeholder="-100..." value=""><br><br>

      目标群（可选下拉）：
      <select id="tgt_sel">
        <option value="">-- 选择群 --</option>
        __GROUP_OPTIONS__
      </select>
      <button type="button" onclick="pickTgt()">使用</button>
      <br><br>
      目标群ID：<input id="target_group_id" name="target_group_id" placeholder="-100..." value=""><br><br>

      用户（可选下拉，可多次追加）：
      <select id="user_sel">
        <option value="">-- 选择用户 --</option>
        __USER_OPTIONS__
      </select>
      <button type="button" onclick="addUser()">追加到用户列表</button>
      <br><br>
      用户ID（多个用逗号分隔）：<input id="user_ids" name="user_ids" placeholder="例如 7796205169,123456789" style="width:560px;"><br><br>

      关键词：<input name="keyword" placeholder="例如 商户订单号 或 订单号,异常 或 *" style="width:560px;"><br><br>

      <script>
      function pickSrc(){
        var v = document.getElementById("src_sel").value;
        if(v){ document.getElementById("source_group_id").value = v; }
      }
      function pickTgt(){
        var v = document.getElementById("tgt_sel").value;
        if(v){ document.getElementById("target_group_id").value = v; }
      }
      function addUser(){
        var v = document.getElementById("user_sel").value;
        if(!v){ return; }
        var input = document.getElementById("user_ids");
        var cur = (input.value || "");
        cur = cur.replaceAll("，", ",");
        cur = cur.trim();
        var arr = [];
        if(cur.length > 0){
          var tmp = cur.split(",");
          for(var i=0;i<tmp.length;i++){
            var t = tmp[i].trim();
            if(t.length > 0){ arr.push(t); }
          }
        }
        for(var j=0;j<arr.length;j++){
          if(arr[j] === v){ return; }
        }
        arr.push(v);
        input.value = arr.join(",");
      }
      </script>

      <hr>
      <b>功能1参数（编辑后发送）</b><br>
      append_text（追加内容，可多行）：<br>
      <textarea name="append_text" rows="4" style="width:720px;"></textarea><br><br>

      <hr>
      <b>功能2参数（查询替换发送）</b><br>
      商户订单号提取正则：<br>
      <input name="merchant_regex" style="width:720px;" value="商户订单号[:：]\\s*([A-Za-z0-9_-]+)"><br><br>
      查询接口URL（lookup_url）：<br>
      <input name="lookup_url" style="width:720px;" value="https://pay.sxjqwork.com/api/anon/robot/payOrder"><br><br>
      替换模板（replace_template，{{pay}} 代表 payOrderId）：<br>
      <input name="replace_template" style="width:720px;" value="支付订单号：{{pay}}"><br><br>

      <hr>
      <b>功能3参数（自动回复）</b><br>
      reply_text（回复内容，可多行）：<br>
      <textarea name="reply_text" rows="4" style="width:720px;" placeholder="例如：已收到，我们会尽快处理。"></textarea><br><br>

      <button type="submit">添加规则</button>
    </form>

    <hr>
    <h3>规则列表</h3>
    <table border="1" cellpadding="8">
      <tr>
        <th>ID</th><th>机器人</th><th>动作</th><th>源群</th><th>目标群</th>
        <th>用户ID(可多个)</th><th>关键词</th><th>状态</th><th>操作</th>
      </tr>
      __RULE_ROWS__
    </table>
    """
    html = (html.replace("__BOT_OPTIONS__", bot_options)
                .replace("__GROUP_OPTIONS__", group_options)
                .replace("__USER_OPTIONS__", user_options)
                .replace("__RULE_ROWS__", rows))
    return html

@app.route("/add_rule", methods=["POST"])
def add_rule():
    bot_id = request.form.get("bot_id", "").strip()
    action_type = request.form.get("action_type", "edit_send").strip()
    source_group_id = request.form.get("source_group_id", "").strip()
    target_group_id = request.form.get("target_group_id", "").strip()
    user_ids = request.form.get("user_ids", "").strip()
    keyword = request.form.get("keyword", "").strip()

    append_text = request.form.get("append_text", "").strip()
    merchant_regex = request.form.get("merchant_regex", "").strip()
    lookup_url = request.form.get("lookup_url", "").strip()
    replace_template = request.form.get("replace_template", "").strip()
    reply_text = request.form.get("reply_text", "").strip()

    if not (bot_id and source_group_id and target_group_id and user_ids and keyword):
        return "<script>alert('❌ 基本字段必须填写（机器人/群/用户/关键词）');window.location.href='/rules';</script>"

    conn = get_db()
    conn.execute("""
        INSERT INTO rules
        (bot_id, action_type, source_group_id, target_group_id, user_id, user_ids, keyword, enabled,
         append_text, merchant_regex, lookup_url, replace_template, reply_text)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
    """, (
        bot_id, action_type, source_group_id, target_group_id,
        user_ids.split(",")[0].strip(),
        user_ids, keyword,
        append_text, merchant_regex, lookup_url, replace_template, reply_text
    ))
    conn.commit()
    conn.close()
    return "<script>alert('✅ 规则添加成功');window.location.href='/rules';</script>"

@app.route("/edit_rule/<int:rule_id>")
def edit_rule(rule_id):
    conn = get_db()
    r = conn.execute("SELECT * FROM rules WHERE id=?", (rule_id,)).fetchone()
    bots = conn.execute("SELECT id, name FROM bots ORDER BY id DESC").fetchall()
    conn.close()
    if not r:
        return "<script>alert('❌ 规则不存在');window.location.href='/rules';</script>"

    bot_options = ""
    for b in bots:
        selected = "selected" if int(r["bot_id"]) == int(b["id"]) else ""
        bot_options += f"<option value='{b['id']}' {selected}>{b['id']} - {b['name']}</option>"

    act = (r["action_type"] or "edit_send").strip()
    sel1 = "selected" if act == "edit_send" else ""
    sel2 = "selected" if act == "lookup_replace" else ""
    sel3 = "selected" if act == "auto_reply" else ""

    users = (r["user_ids"] or r["user_id"] or "").strip()

    return f"""
    <h2>✏️ 编辑规则 #{r['id']}</h2>
    <p><a href="/rules">⬅️ 返回规则列表</a></p>
    <hr>

    <form action="/update_rule/{r['id']}" method="post">
      绑定机器人：<select name="bot_id">{bot_options}</select><br><br>

      动作类型：
      <select name="action_type">
        <option value="edit_send" {sel1}>功能1：编辑后发送</option>
        <option value="lookup_replace" {sel2}>功能2：查询替换发送</option>
        <option value="auto_reply" {sel3}>功能3：自动回复</option>
      </select><br><br>

      源群ID：<input name="source_group_id" value="{r['source_group_id']}"><br><br>
      目标群ID：<input name="target_group_id" value="{r['target_group_id']}"><br><br>

      用户ID（多个用逗号分隔）：<input name="user_ids" value="{users}" style="width:560px;"><br><br>
      关键词：<input name="keyword" value="{r['keyword']}" style="width:560px;"><br><br>

      状态：
      <select name="enabled">
        <option value="1" {"selected" if r["enabled"] == 1 else ""}>启用</option>
        <option value="0" {"selected" if r["enabled"] == 0 else ""}>禁用</option>
      </select><br><br>

      <hr>
      <b>功能1参数</b><br>
      append_text：<br>
      <textarea name="append_text" rows="4" style="width:720px;">{r["append_text"] or ""}</textarea><br><br>

      <hr>
      <b>功能2参数</b><br>
      merchant_regex：<input name="merchant_regex" style="width:720px;" value="{r["merchant_regex"] or ""}"><br><br>
      lookup_url：<input name="lookup_url" style="width:720px;" value="{r["lookup_url"] or ""}"><br><br>
      replace_template：<input name="replace_template" style="width:720px;" value="{r["replace_template"] or ""}"><br><br>

      <hr>
      <b>功能3参数</b><br>
      reply_text：<br>
      <textarea name="reply_text" rows="4" style="width:720px;">{r["reply_text"] or ""}</textarea><br><br>

      <button type="submit">保存</button>
    </form>
    """

@app.route("/update_rule/<int:rule_id>", methods=["POST"])
def update_rule(rule_id):
    bot_id = request.form.get("bot_id", "").strip()
    action_type = request.form.get("action_type", "edit_send").strip()
    source_group_id = request.form.get("source_group_id", "").strip()
    target_group_id = request.form.get("target_group_id", "").strip()
    user_ids = request.form.get("user_ids", "").strip()
    keyword = request.form.get("keyword", "").strip()
    enabled = 1 if request.form.get("enabled") == "1" else 0

    append_text = request.form.get("append_text", "").strip()
    merchant_regex = request.form.get("merchant_regex", "").strip()
    lookup_url = request.form.get("lookup_url", "").strip()
    replace_template = request.form.get("replace_template", "").strip()
    reply_text = request.form.get("reply_text", "").strip()

    if not (bot_id and source_group_id and target_group_id and user_ids and keyword):
        return "<script>alert('❌ 基本字段必须填写（机器人/群/用户/关键词）');window.history.back();</script>"

    conn = get_db()
    conn.execute("""
        UPDATE rules
        SET bot_id=?, action_type=?, source_group_id=?, target_group_id=?,
            user_id=?, user_ids=?, keyword=?, enabled=?,
            append_text=?, merchant_regex=?, lookup_url=?, replace_template=?, reply_text=?
        WHERE id=?
    """, (
        bot_id, action_type, source_group_id, target_group_id,
        user_ids.split(",")[0].strip(),
        user_ids, keyword, enabled,
        append_text, merchant_regex, lookup_url, replace_template, reply_text,
        rule_id
    ))
    conn.commit()
    conn.close()
    return "<script>alert('✅ 保存成功');window.location.href='/rules';</script>"

@app.route("/toggle_rule/<int:rule_id>")
def toggle_rule(rule_id):
    conn = get_db()
    r = conn.execute("SELECT enabled FROM rules WHERE id=?", (rule_id,)).fetchone()
    if r:
        new_status = 0 if r["enabled"] else 1
        conn.execute("UPDATE rules SET enabled=? WHERE id=?", (new_status, rule_id))
        conn.commit()
    conn.close()
    return "<script>alert('🔄 已切换');window.location.href='/rules';</script>"

@app.route("/delete_rule/<int:rule_id>")
def delete_rule(rule_id):
    conn = get_db()
    conn.execute("DELETE FROM rules WHERE id=?", (rule_id,))
    conn.commit()
    conn.close()
    return "<script>alert('🗑️ 已删除');window.location.href='/rules';</script>"


# -------------------- Logs --------------------
@app.route("/logs")
def logs_page():
    return """
    <h2>📜 日志</h2>
    <p>
      <a href="/">⬅️ 返回</a> |
      <a href="/bots">🔑 机器人</a> |
      <a href="/rules">📌 规则</a> |
      <a href="/users">👤 用户ID</a> |
      <a href="/groups">👥 群ID</a>
    </p>
    <hr>

    <div id="logs"></div>

    <script>
    async function loadLogs(){
      const res = await fetch('/logs_json');
      const data = await res.json();

      let html = "<table border='1' cellpadding='8'>";
      html += "<tr><th>ID</th><th>时间</th><th>机器人</th><th>规则</th><th>类型</th><th>内容</th></tr>";

      data.forEach(l => {
        html += `<tr>
          <td>${l.id}</td>
          <td>${l.ts}</td>
          <td>${l.bot_id ?? ""}</td>
          <td>${l.rule_id ?? ""}</td>
          <td>${l.message_type ?? ""}</td>
          <td style="max-width:700px; white-space:pre-wrap;">${(l.message_text ?? "").replaceAll("<","&lt;").replaceAll(">","&gt;")}</td>
        </tr>`;
      });

      html += "</table>";
      document.getElementById("logs").innerHTML = html;
    }

    loadLogs();
    setInterval(loadLogs, 3000);
    </script>
    """

@app.route("/logs_json")
def logs_json():
    conn = get_db()
    rows = conn.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 400").fetchall()
    conn.close()
    return jsonify([{
        "id": r["id"],
        "ts": r["ts"],
        "bot_id": r["bot_id"],
        "rule_id": r["rule_id"],
        "message_type": r["message_type"],
        "message_text": r["message_text"],
    } for r in rows])

if __name__ == "__main__":
    init_db_if_needed()
    port = int(os.environ.get("PORT", 8888))
    print(f"✅ 后台启动成功：http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port)
