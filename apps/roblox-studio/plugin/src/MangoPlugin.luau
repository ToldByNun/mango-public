--[[
	Mango — local Roblox Studio plugin
	Talks to mango-studio-host on http://127.0.0.1:17880 (long-poll).

	Install: copy this file to
	  %LOCALAPPDATA%\Roblox\Plugins\MangoPlugin.luau
	or use Install-StudioPlugin.ps1, then restart Studio.
]]

local HttpService = game:GetService("HttpService")
local Selection = game:GetService("Selection")
local ChangeHistoryService = game:GetService("ChangeHistoryService")
local RunService = game:GetService("RunService")

if not plugin then
	warn("[Mango] Must run as a Studio plugin")
	return
end

local DEFAULT_PORT = 17880
local HOST = "127.0.0.1"

local state = {
	port = plugin:GetSetting("MangoPort") or DEFAULT_PORT,
	online = false,
	busy = false,
	sessionId = HttpService:GenerateGUID(false),
	eventSince = 0,
	pollActive = false,
	eventActive = false,
	pendingConfirm = nil, -- { requestId, summary, resolve }
	transcript = {},
	confirmPropThreshold = 1,
}

local function baseUrl()
	return ("http://%s:%d"):format(HOST, tonumber(state.port) or DEFAULT_PORT)
end

local function httpJson(method, path, bodyTable)
	local url = baseUrl() .. path
	local ok, result = pcall(function()
		local req = {
			Url = url,
			Method = method,
			Headers = { ["Content-Type"] = "application/json" },
		}
		if bodyTable ~= nil then
			req.Body = HttpService:JSONEncode(bodyTable)
		end
		return HttpService:RequestAsync(req)
	end)
	if not ok then
		return false, tostring(result)
	end
	if not result.Success then
		return false, ("HTTP %s: %s"):format(tostring(result.StatusCode), tostring(result.Body))
	end
	local decoded = nil
	if result.Body and result.Body ~= "" then
		local dok, data = pcall(function()
			return HttpService:JSONDecode(result.Body)
		end)
		if dok then
			decoded = data
		else
			decoded = { raw = result.Body }
		end
	end
	return true, decoded or {}
end

-- ─── DataModel helpers ─────────────────────────────────────────────

local DENY_SERVICES = {
	CoreGui = true,
	PluginGuiService = true,
	RobloxPluginGuiService = true,
	CorePackages = true,
}

local function splitPath(path)
	path = tostring(path or ""):gsub("^game%.?", ""):gsub("^/", "")
	local parts = {}
	for part in string.gmatch(path, "[^%.%/]+") do
		table.insert(parts, part)
	end
	return parts
end

local function resolvePath(path)
	if path == nil or path == "" or path == "game" then
		return game
	end
	local parts = splitPath(path)
	local cur = game
	for _, name in ipairs(parts) do
		local child = cur:FindFirstChild(name)
		if not child then
			-- Services are often GetService, not FindFirstChild
			local ok, svc = pcall(function()
				return game:GetService(name)
			end)
			if ok and svc and svc.Parent == game then
				child = svc
			end
		end
		if not child then
			return nil, ("not found: %s (at %s)"):format(path, name)
		end
		cur = child
	end
	return cur, nil
end

local function instancePath(inst)
	if not inst or inst == game then
		return "game"
	end
	local parts = {}
	local cur = inst
	while cur and cur ~= game do
		table.insert(parts, 1, cur.Name)
		cur = cur.Parent
	end
	return "game." .. table.concat(parts, ".")
end

local function isDenied(inst)
	if not inst then
		return true
	end
	local cur = inst
	while cur and cur ~= game do
		if DENY_SERVICES[cur.ClassName] or DENY_SERVICES[cur.Name] then
			return true
		end
		cur = cur.Parent
	end
	return false
end

local function convertValue(current, value)
	if typeof(current) == "Vector3" and type(value) == "table" then
		return Vector3.new(value.X or value.x or 0, value.Y or value.y or 0, value.Z or value.z or 0)
	end
	if typeof(current) == "Color3" and type(value) == "table" then
		return Color3.new(value.R or value.r or 0, value.G or value.g or 0, value.B or value.b or 0)
	end
	if typeof(current) == "EnumItem" and type(value) == "string" then
		local enumType = current.EnumType
		local ok, item = pcall(function()
			return enumType[value]
		end)
		if ok then
			return item
		end
	end
	return value
end

local function treeNode(inst, depth, maxNodes, counter)
	if counter.n >= maxNodes then
		return nil
	end
	counter.n += 1
	local node = {
		path = instancePath(inst),
		name = inst.Name,
		className = inst.ClassName,
		children = {},
	}
	if depth <= 0 then
		return node
	end
	for _, child in ipairs(inst:GetChildren()) do
		if not isDenied(child) then
			local c = treeNode(child, depth - 1, maxNodes, counter)
			if c then
				table.insert(node.children, c)
			end
		end
	end
	return node
end

local SCRIPT_CLASSES = {
	Script = true,
	LocalScript = true,
	ModuleScript = true,
}

local function applyEdit(source, old, new)
	if old == nil or old == "" then
		return nil, "empty_old"
	end
	local count = 0
	local start = 1
	while true do
		local i, j = string.find(source, old, start, true)
		if not i then
			break
		end
		count += 1
		start = j + 1
		if count > 1 then
			break
		end
	end
	if count == 0 then
		return nil, "not_found"
	end
	if count > 1 then
		return nil, "ambiguous"
	end
	local i, j = string.find(source, old, 1, true)
	local updated = string.sub(source, 1, i - 1) .. new .. string.sub(source, j + 1)
	local ctxStart = math.max(1, i - 80)
	local ctxEnd = math.min(#updated, i + #new + 80)
	local snippet = string.sub(updated, ctxStart, ctxEnd)
	return updated, nil, snippet
end

local function executeTool(tool, args)
	args = args or {}
	if tool == "rbx_tree" then
		local path = args.path or "game"
		local inst, err = resolvePath(path)
		if not inst then
			return { ok = false, error = err }
		end
		local counter = { n = 0 }
		local tree = treeNode(inst, tonumber(args.depth) or 3, tonumber(args.max_nodes) or 200, counter)
		return { ok = true, tree = tree, nodes = counter.n }
	end

	if tool == "rbx_sel" then
		if args.paths then
			local list = {}
			for _, p in ipairs(args.paths) do
				local inst = resolvePath(p)
				if inst then
					table.insert(list, inst)
				end
			end
			Selection:Set(list)
		end
		local selected = {}
		for _, inst in ipairs(Selection:Get()) do
			table.insert(selected, instancePath(inst))
		end
		return { ok = true, paths = selected }
	end

	if tool == "rbx_read" then
		local inst, err = resolvePath(args.path)
		if not inst then
			return { ok = false, error = err }
		end
		local what = args.what or "source"
		if what == "source" then
			if not SCRIPT_CLASSES[inst.ClassName] then
				return { ok = false, error = "not_a_script", className = inst.ClassName }
			end
			return { ok = true, path = instancePath(inst), source = inst.Source, className = inst.ClassName }
		end
		local props = {
			Name = inst.Name,
			ClassName = inst.ClassName,
			Parent = inst.Parent and instancePath(inst.Parent) or "",
		}
		return { ok = true, path = instancePath(inst), props = props }
	end

	if tool == "rbx_edit" then
		local inst, err = resolvePath(args.path)
		if not inst then
			return { ok = false, error = err }
		end
		if not SCRIPT_CLASSES[inst.ClassName] then
			return { ok = false, error = "not_a_script" }
		end
		if isDenied(inst) then
			return { ok = false, error = "denied" }
		end
		local updated, e2, snippet = applyEdit(inst.Source, args.old or "", args.new or "")
		if not updated then
			return { ok = false, error = e2 }
		end
		ChangeHistoryService:SetWaypoint("Mango rbx_edit")
		inst.Source = updated
		ChangeHistoryService:SetWaypoint("Mango rbx_edit done")
		return { ok = true, path = instancePath(inst), snippet = snippet, bytes = #updated }
	end

	if tool == "rbx_create" then
		local parent, err = resolvePath(args.parent)
		if not parent then
			return { ok = false, error = err }
		end
		if isDenied(parent) then
			return { ok = false, error = "denied" }
		end
		local className = args.className or args.class_name
		if not className or className == "" then
			return { ok = false, error = "missing_className" }
		end
		local okc, inst = pcall(function()
			return Instance.new(className)
		end)
		if not okc or not inst then
			return { ok = false, error = "bad_className", detail = tostring(inst) }
		end
		if args.name and args.name ~= "" then
			inst.Name = args.name
		end
		if SCRIPT_CLASSES[className] and args.source and args.source ~= "" then
			inst.Source = args.source
		elseif SCRIPT_CLASSES[className] then
			inst.Source = "-- mango: stub\n"
		end
		ChangeHistoryService:SetWaypoint("Mango rbx_create")
		inst.Parent = parent
		ChangeHistoryService:SetWaypoint("Mango rbx_create done")
		return { ok = true, path = instancePath(inst), className = className }
	end

	if tool == "rbx_prop" then
		local paths = args.paths
		if (not paths or #paths == 0) and args.path then
			paths = { args.path }
		end
		if not paths or #paths == 0 then
			return { ok = false, error = "missing_paths" }
		end
		local propName = args.propertyName or args.property_name
		if not propName then
			return { ok = false, error = "missing_property" }
		end
		ChangeHistoryService:SetWaypoint("Mango rbx_prop")
		local updated = {}
		for _, p in ipairs(paths) do
			local inst, e = resolvePath(p)
			if not inst then
				return { ok = false, error = e }
			end
			if isDenied(inst) then
				return { ok = false, error = "denied", path = p }
			end
			local okGet, current = pcall(function()
				return inst[propName]
			end)
			if not okGet then
				return { ok = false, error = "bad_property", path = p, detail = tostring(current) }
			end
			local converted = convertValue(current, args.value)
			local okSet, setErr = pcall(function()
				inst[propName] = converted
			end)
			if not okSet then
				return { ok = false, error = "set_failed", path = p, detail = tostring(setErr) }
			end
			table.insert(updated, p)
		end
		ChangeHistoryService:SetWaypoint("Mango rbx_prop done")
		return { ok = true, paths = updated, propertyName = propName }
	end

	if tool == "rbx_delete" then
		local inst, err = resolvePath(args.path)
		if not inst then
			return { ok = false, error = err }
		end
		if inst == game or isDenied(inst) then
			return { ok = false, error = "denied" }
		end
		local path = instancePath(inst)
		ChangeHistoryService:SetWaypoint("Mango rbx_delete")
		inst:Destroy()
		ChangeHistoryService:SetWaypoint("Mango rbx_delete done")
		return { ok = true, deleted = path }
	end

	return { ok = false, error = "unknown_tool", tool = tool }
end

-- ─── UI ────────────────────────────────────────────────────────────

local toolbar = plugin:CreateToolbar("Mango")
local button = toolbar:CreateButton("Mango", "Open Mango agent panel", "")

local widgetInfo = DockWidgetPluginGuiInfo.new(
	Enum.InitialDockState.Right,
	false, -- initially enabled
	false,
	420,
	560,
	320,
	400
)
local widget = plugin:CreateDockWidgetPluginGui("MangoAgent", widgetInfo)
widget.Title = "Mango"

local root = Instance.new("Frame")
root.Size = UDim2.fromScale(1, 1)
root.BackgroundColor3 = Color3.fromRGB(30, 30, 32)
root.BorderSizePixel = 0
root.Parent = widget

local function mkLabel(parent, text, y, h)
	local l = Instance.new("TextLabel")
	l.BackgroundTransparency = 1
	l.Position = UDim2.new(0, 8, 0, y)
	l.Size = UDim2.new(1, -16, 0, h or 18)
	l.Font = Enum.Font.Gotham
	l.TextSize = 13
	l.TextXAlignment = Enum.TextXAlignment.Left
	l.TextColor3 = Color3.fromRGB(220, 220, 220)
	l.Text = text
	l.Parent = parent
	return l
end

local statusLabel = mkLabel(root, "Host: checking…", 8, 20)
statusLabel.TextColor3 = Color3.fromRGB(180, 180, 100)

local transcript = Instance.new("ScrollingFrame")
transcript.Position = UDim2.new(0, 8, 0, 36)
transcript.Size = UDim2.new(1, -16, 1, -160)
transcript.BackgroundColor3 = Color3.fromRGB(22, 22, 24)
transcript.BorderSizePixel = 0
transcript.ScrollBarThickness = 6
transcript.CanvasSize = UDim2.new(0, 0, 0, 0)
transcript.Parent = root

local transcriptLayout = Instance.new("UIListLayout")
transcriptLayout.Padding = UDim.new(0, 4)
transcriptLayout.Parent = transcript

local confirmFrame = Instance.new("Frame")
confirmFrame.Visible = false
confirmFrame.Position = UDim2.new(0, 8, 1, -150)
confirmFrame.Size = UDim2.new(1, -16, 0, 56)
confirmFrame.BackgroundColor3 = Color3.fromRGB(60, 40, 20)
confirmFrame.BorderSizePixel = 0
confirmFrame.Parent = root
confirmFrame.ZIndex = 5

local confirmLabel = mkLabel(confirmFrame, "Confirm?", 4, 24)
confirmLabel.Size = UDim2.new(1, -16, 0, 24)
confirmLabel.TextWrapped = true
confirmLabel.ZIndex = 6

local allowBtn = Instance.new("TextButton")
allowBtn.Size = UDim2.new(0, 80, 0, 22)
allowBtn.Position = UDim2.new(0, 8, 0, 30)
allowBtn.Text = "Allow"
allowBtn.Font = Enum.Font.GothamBold
allowBtn.TextSize = 12
allowBtn.BackgroundColor3 = Color3.fromRGB(40, 120, 60)
allowBtn.TextColor3 = Color3.new(1, 1, 1)
allowBtn.Parent = confirmFrame
allowBtn.ZIndex = 6

local denyBtn = Instance.new("TextButton")
denyBtn.Size = UDim2.new(0, 80, 0, 22)
denyBtn.Position = UDim2.new(0, 96, 0, 30)
denyBtn.Text = "Deny"
denyBtn.Font = Enum.Font.GothamBold
denyBtn.TextSize = 12
denyBtn.BackgroundColor3 = Color3.fromRGB(140, 40, 40)
denyBtn.TextColor3 = Color3.new(1, 1, 1)
denyBtn.Parent = confirmFrame
denyBtn.ZIndex = 6

local composer = Instance.new("TextBox")
composer.Position = UDim2.new(0, 8, 1, -90)
composer.Size = UDim2.new(1, -16, 0, 50)
composer.BackgroundColor3 = Color3.fromRGB(40, 40, 44)
composer.TextColor3 = Color3.fromRGB(230, 230, 230)
composer.PlaceholderText = "Ask Mango to edit this Place…"
composer.PlaceholderColor3 = Color3.fromRGB(120, 120, 120)
composer.Text = ""
composer.TextXAlignment = Enum.TextXAlignment.Left
composer.TextYAlignment = Enum.TextYAlignment.Top
composer.ClearTextOnFocus = false
composer.MultiLine = true
composer.TextWrapped = true
composer.Font = Enum.Font.Gotham
composer.TextSize = 13
composer.Parent = root

local sendBtn = Instance.new("TextButton")
sendBtn.Position = UDim2.new(0, 8, 1, -34)
sendBtn.Size = UDim2.new(0, 80, 0, 26)
sendBtn.Text = "Send"
sendBtn.Font = Enum.Font.GothamBold
sendBtn.TextSize = 13
sendBtn.BackgroundColor3 = Color3.fromRGB(50, 100, 180)
sendBtn.TextColor3 = Color3.new(1, 1, 1)
sendBtn.Parent = root

local cancelBtn = Instance.new("TextButton")
cancelBtn.Position = UDim2.new(0, 96, 1, -34)
cancelBtn.Size = UDim2.new(0, 80, 0, 26)
cancelBtn.Text = "Cancel"
cancelBtn.Font = Enum.Font.Gotham
cancelBtn.TextSize = 13
cancelBtn.BackgroundColor3 = Color3.fromRGB(80, 80, 80)
cancelBtn.TextColor3 = Color3.new(1, 1, 1)
cancelBtn.Parent = root

local offlineHint = mkLabel(root, "", 1, -34)
offlineHint.Position = UDim2.new(0, 188, 1, -34)
offlineHint.Size = UDim2.new(1, -196, 0, 26)
offlineHint.TextSize = 11
offlineHint.TextColor3 = Color3.fromRGB(180, 120, 80)
offlineHint.Text = ""

local function appendLine(text, color)
	local line = Instance.new("TextLabel")
	line.BackgroundTransparency = 1
	line.Size = UDim2.new(1, -8, 0, 0)
	line.AutomaticSize = Enum.AutomaticSize.Y
	line.Font = Enum.Font.Code
	line.TextSize = 12
	line.TextXAlignment = Enum.TextXAlignment.Left
	line.TextYAlignment = Enum.TextYAlignment.Top
	line.TextWrapped = true
	line.TextColor3 = color or Color3.fromRGB(200, 200, 200)
	line.Text = text
	line.Parent = transcript
	task.defer(function()
		transcript.CanvasSize = UDim2.new(0, 0, 0, transcriptLayout.AbsoluteContentSize.Y + 8)
		transcript.CanvasPosition = Vector2.new(0, math.max(0, transcriptLayout.AbsoluteContentSize.Y))
	end)
end

local function setStatus(text, color)
	statusLabel.Text = text
	if color then
		statusLabel.TextColor3 = color
	end
end

local function selectionContext()
	local parts = {}
	for _, inst in ipairs(Selection:Get()) do
		table.insert(parts, instancePath(inst))
	end
	if #parts == 0 then
		return nil
	end
	return table.concat(parts, "\n")
end

local function showConfirm(summary)
	local bindable = Instance.new("BindableEvent")
	state.pendingConfirm = true
	confirmLabel.Text = summary or "Agent wants a destructive action — allow?"
	confirmFrame.Visible = true
	local decided = false
	local allowed = false
	local conn1, conn2
	conn1 = allowBtn.MouseButton1Click:Connect(function()
		if decided then
			return
		end
		decided = true
		allowed = true
		bindable:Fire()
	end)
	conn2 = denyBtn.MouseButton1Click:Connect(function()
		if decided then
			return
		end
		decided = true
		allowed = false
		bindable:Fire()
	end)
	bindable.Event:Wait()
	conn1:Disconnect()
	conn2:Disconnect()
	confirmFrame.Visible = false
	state.pendingConfirm = false
	bindable:Destroy()
	return allowed
end

local function handleStudioRequest(req)
	if not req or not req.request_id then
		return
	end
	local tool = req.tool
	local args = req.args or {}
	if req.requires_confirm then
		local allowed = showConfirm(req.confirm_summary or ("Allow " .. tostring(tool) .. "?"))
		if not allowed then
			httpJson("POST", "/v1/studio/result", {
				request_id = req.request_id,
				ok = false,
				error = "user_denied",
			})
			appendLine("Denied: " .. tostring(req.confirm_summary), Color3.fromRGB(220, 140, 100))
			return
		end
	end
	local result = executeTool(tool, args)
	result.request_id = req.request_id
	httpJson("POST", "/v1/studio/result", result)
	if result.ok then
		appendLine(("✓ %s"):format(tool), Color3.fromRGB(120, 200, 140))
	else
		appendLine(("✗ %s: %s"):format(tool, tostring(result.error)), Color3.fromRGB(220, 120, 120))
	end
end

local function pollStudioLoop()
	if state.pollActive then
		return
	end
	state.pollActive = true
	task.spawn(function()
		local backoff = 0.5
		while state.pollActive do
			if RunService:IsRunning() then
				task.wait(1)
			else
				local ok, data = httpJson("GET", "/v1/studio/poll?wait=20")
				if ok and data and data.request then
					backoff = 0.5
					local success, err = pcall(handleStudioRequest, data.request)
					if not success then
						appendLine("Tool handler error: " .. tostring(err), Color3.fromRGB(220, 80, 80))
						httpJson("POST", "/v1/studio/result", {
							request_id = data.request.request_id,
							ok = false,
							error = "plugin_error",
							detail = tostring(err),
						})
					end
				elseif not ok then
					task.wait(backoff)
					backoff = math.min(backoff * 1.3, 8)
				end
			end
		end
	end)
end

local function pollEventsLoop()
	if state.eventActive then
		return
	end
	state.eventActive = true
	task.spawn(function()
		while state.eventActive do
			local ok, data = httpJson("GET", ("/v1/events?since=%d&wait=20"):format(state.eventSince))
			if ok and data and data.events then
				for _, ev in ipairs(data.events) do
					local seq = tonumber(ev._seq) or 0
					if seq > state.eventSince then
						state.eventSince = seq
					end
					local name = ev.event or ""
					local payload = ev.payload or {}
					if name == "agent.token" or name == "agent.thought" then
						local t = payload.text or payload.token or ""
						if t ~= "" then
							appendLine(t, Color3.fromRGB(160, 160, 180))
						end
					elseif name == "agent.tool" then
						appendLine(("→ %s"):format(payload.name or payload.tool or "tool"), Color3.fromRGB(100, 180, 220))
					elseif name == "agent.final" then
						appendLine(payload.text or payload.summary or "(done)", Color3.fromRGB(200, 220, 180))
					elseif name == "agent.error" then
						appendLine("Error: " .. tostring(payload.text or payload.error), Color3.fromRGB(220, 100, 100))
					elseif name == "agent.stopped" then
						state.busy = false
						setStatus(
							state.online and "Host: online" or "Host: offline",
							state.online and Color3.fromRGB(120, 200, 120) or Color3.fromRGB(200, 120, 80)
						)
					elseif name == "agent.started" then
						state.busy = true
						setStatus("Host: running…", Color3.fromRGB(100, 160, 220))
					end
				end
			else
				task.wait(1)
			end
		end
	end)
end

local function refreshHealth()
	local ok, data = httpJson("GET", "/health")
	if ok and data and data.status == "ok" then
		state.online = true
		offlineHint.Text = ""
		local sid = data.sidecar and "sidecar ok" or "sidecar down"
		local model = data.model_loaded and " · model" or ""
		setStatus(("Host: online (%s%s)"):format(sid, model), Color3.fromRGB(120, 200, 120))
		return true
	end
	state.online = false
	setStatus("Host: offline", Color3.fromRGB(200, 120, 80))
	offlineHint.Text = "Start mango-studio-host"
	return false
end

local function sendGoal()
	local goal = composer.Text
	if not goal or goal:match("^%s*$") then
		return
	end
	if not refreshHealth() then
		appendLine("Cannot send — host offline. Run: python -m mango_studio_host", Color3.fromRGB(220, 140, 80))
		return
	end
	appendLine("You: " .. goal, Color3.fromRGB(230, 230, 230))
	composer.Text = ""
	state.busy = true
	local ok, data = httpJson("POST", "/v1/run", {
		session_id = state.sessionId,
		goal = goal,
		mode = "roblox",
		thinking_level = "off",
		selection = selectionContext(),
	})
	if not ok then
		state.busy = false
		appendLine("Run failed: " .. tostring(data), Color3.fromRGB(220, 100, 100))
		return
	end
	setStatus("Host: running…", Color3.fromRGB(100, 160, 220))
end

sendBtn.MouseButton1Click:Connect(sendGoal)
cancelBtn.MouseButton1Click:Connect(function()
	httpJson("POST", "/v1/cancel", {})
	state.busy = false
	appendLine("(cancelled)", Color3.fromRGB(180, 180, 100))
end)

button.Click:Connect(function()
	widget.Enabled = not widget.Enabled
	if widget.Enabled then
		refreshHealth()
		pollStudioLoop()
		pollEventsLoop()
	end
end)

-- Health tick
task.spawn(function()
	while true do
		if widget.Enabled then
			refreshHealth()
		end
		task.wait(5)
	end
end)

appendLine("Mango Studio plugin ready. Start mango-studio-host, then Send a goal.", Color3.fromRGB(140, 160, 180))
