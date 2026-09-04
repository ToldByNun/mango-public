--[[
	Mango — local Roblox Studio plugin
	Talks to mango-studio-host on http://127.0.0.1:17880 (long-poll).

	Install: use Install-StudioPlugin.ps1 / MangoStudio.cmd
	(copies as MangoPlugin.lua — Studio ignores .luau in PluginsDir).
	Then fully quit and reopen Studio.
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
	pendingConfirm = nil,
	transcript = {},
	confirmPropThreshold = 1,
	models = {},
	modelPath = "",
	modelLabel = "No model",
	pickerOpen = false,
	thinkingOpen = false,
	thinkingLevel = plugin:GetSetting("MangoThinkingLevel") or "off",
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

-- ─── UI (Mango Electron composer look) ─────────────────────────────

-- Tokens from apps/electron/src/renderer/src/styles/tokens.css
local C = {
	surface0 = Color3.fromRGB(14, 13, 12), -- #0e0d0c
	surface1 = Color3.fromRGB(22, 20, 18), -- #161412
	surface2 = Color3.fromRGB(28, 26, 24), -- #1c1a18
	surface3 = Color3.fromRGB(37, 34, 31), -- #25221f
	border = Color3.fromRGB(46, 42, 38), -- #2e2a26
	text = Color3.fromRGB(245, 242, 237), -- #f5f2ed
	muted = Color3.fromRGB(168, 159, 148), -- #a89f94
	dim = Color3.fromRGB(122, 114, 104), -- #7a7268
	accent = Color3.fromRGB(232, 148, 58), -- #e8943a
	accentOn = Color3.fromRGB(26, 18, 8), -- #1a1208
	ok = Color3.fromRGB(61, 186, 110),
	warn = Color3.fromRGB(229, 162, 58),
	danger = Color3.fromRGB(232, 93, 76),
}

local function corner(parent, px)
	local c = Instance.new("UICorner")
	c.CornerRadius = UDim.new(0, px or 8)
	c.Parent = parent
	return c
end

local function pad(parent, t, r, b, l)
	local p = Instance.new("UIPadding")
	p.PaddingTop = UDim.new(0, t or 0)
	p.PaddingRight = UDim.new(0, r or t or 0)
	p.PaddingBottom = UDim.new(0, b or t or 0)
	p.PaddingLeft = UDim.new(0, l or r or t or 0)
	p.Parent = parent
	return p
end

local toolbar = plugin:CreateToolbar("Mango")
local button = toolbar:CreateButton("Mango", "Open Mango agent panel", "")

local widgetInfo = DockWidgetPluginGuiInfo.new(
	Enum.InitialDockState.Right,
	false,
	false,
	440,
	620,
	340,
	420
)
local widget = plugin:CreateDockWidgetPluginGui("MangoAgent", widgetInfo)
widget.Title = "Mango"

local root = Instance.new("Frame")
root.Size = UDim2.fromScale(1, 1)
root.BackgroundColor3 = C.surface0
root.BorderSizePixel = 0
root.Parent = widget

-- Header
local header = Instance.new("Frame")
header.Size = UDim2.new(1, 0, 0, 36)
header.BackgroundColor3 = C.surface1
header.BorderSizePixel = 0
header.Parent = root

local headerRule = Instance.new("Frame")
headerRule.Size = UDim2.new(1, 0, 0, 1)
headerRule.Position = UDim2.new(0, 0, 1, -1)
headerRule.BackgroundColor3 = C.border
headerRule.BorderSizePixel = 0
headerRule.Parent = header

local brandDot = Instance.new("Frame")
brandDot.Size = UDim2.fromOffset(10, 10)
brandDot.Position = UDim2.new(0, 14, 0.5, -5)
brandDot.BackgroundColor3 = C.accent
brandDot.BorderSizePixel = 0
brandDot.Parent = header
corner(brandDot, 3)

local brandLabel = Instance.new("TextLabel")
brandLabel.BackgroundTransparency = 1
brandLabel.Position = UDim2.new(0, 32, 0, 0)
brandLabel.Size = UDim2.new(0, 80, 1, 0)
brandLabel.Font = Enum.Font.GothamBold
brandLabel.TextSize = 14
brandLabel.TextXAlignment = Enum.TextXAlignment.Left
brandLabel.TextColor3 = C.text
brandLabel.Text = "Mango"
brandLabel.Parent = header

local statusLabel = Instance.new("TextLabel")
statusLabel.BackgroundTransparency = 1
statusLabel.Position = UDim2.new(0, 100, 0, 0)
statusLabel.Size = UDim2.new(1, -112, 1, 0)
statusLabel.Font = Enum.Font.Gotham
statusLabel.TextSize = 12
statusLabel.TextXAlignment = Enum.TextXAlignment.Right
statusLabel.TextColor3 = C.dim
statusLabel.Text = "Host: checking…"
statusLabel.Parent = header

-- Transcript
local transcript = Instance.new("ScrollingFrame")
transcript.Position = UDim2.new(0, 0, 0, 36)
transcript.Size = UDim2.new(1, 0, 1, -158)
transcript.BackgroundColor3 = C.surface0
transcript.BorderSizePixel = 0
transcript.ScrollBarThickness = 4
transcript.ScrollBarImageColor3 = C.border
transcript.CanvasSize = UDim2.new(0, 0, 0, 0)
transcript.AutomaticCanvasSize = Enum.AutomaticSize.Y
transcript.Parent = root
pad(transcript, 12, 14, 8, 14)

local transcriptLayout = Instance.new("UIListLayout")
transcriptLayout.Padding = UDim.new(0, 8)
transcriptLayout.SortOrder = Enum.SortOrder.LayoutOrder
transcriptLayout.Parent = transcript

-- Confirm strip (above composer)
local confirmFrame = Instance.new("Frame")
confirmFrame.Visible = false
confirmFrame.AnchorPoint = Vector2.new(0, 1)
confirmFrame.Position = UDim2.new(0, 12, 1, -130)
confirmFrame.Size = UDim2.new(1, -24, 0, 52)
confirmFrame.BackgroundColor3 = Color3.fromRGB(48, 32, 18)
confirmFrame.BorderSizePixel = 0
confirmFrame.ZIndex = 8
confirmFrame.Parent = root
corner(confirmFrame, 10)
pad(confirmFrame, 8, 10, 8, 10)

local confirmLabel = Instance.new("TextLabel")
confirmLabel.BackgroundTransparency = 1
confirmLabel.Size = UDim2.new(1, -170, 1, 0)
confirmLabel.Font = Enum.Font.Gotham
confirmLabel.TextSize = 12
confirmLabel.TextXAlignment = Enum.TextXAlignment.Left
confirmLabel.TextYAlignment = Enum.TextYAlignment.Center
confirmLabel.TextWrapped = true
confirmLabel.TextColor3 = C.text
confirmLabel.Text = "Confirm?"
confirmLabel.ZIndex = 9
confirmLabel.Parent = confirmFrame

local allowBtn = Instance.new("TextButton")
allowBtn.AnchorPoint = Vector2.new(1, 0.5)
allowBtn.Position = UDim2.new(1, -88, 0.5, 0)
allowBtn.Size = UDim2.fromOffset(72, 28)
allowBtn.Text = "Allow"
allowBtn.Font = Enum.Font.GothamBold
allowBtn.TextSize = 12
allowBtn.BackgroundColor3 = C.ok
allowBtn.TextColor3 = C.accentOn
allowBtn.AutoButtonColor = true
allowBtn.ZIndex = 9
allowBtn.Parent = confirmFrame
corner(allowBtn, 8)

local denyBtn = Instance.new("TextButton")
denyBtn.AnchorPoint = Vector2.new(1, 0.5)
denyBtn.Position = UDim2.new(1, -8, 0.5, 0)
denyBtn.Size = UDim2.fromOffset(72, 28)
denyBtn.Text = "Deny"
denyBtn.Font = Enum.Font.GothamBold
denyBtn.TextSize = 12
denyBtn.BackgroundColor3 = C.danger
denyBtn.TextColor3 = Color3.new(1, 1, 1)
denyBtn.AutoButtonColor = true
denyBtn.ZIndex = 9
denyBtn.Parent = confirmFrame
corner(denyBtn, 8)

-- Composer bar (screenshot match)
local composerWrap = Instance.new("Frame")
composerWrap.AnchorPoint = Vector2.new(0, 1)
composerWrap.Position = UDim2.new(0, 12, 1, -12)
composerWrap.Size = UDim2.new(1, -24, 0, 108)
composerWrap.BackgroundTransparency = 1
composerWrap.Parent = root

local composerBar = Instance.new("Frame")
composerBar.Size = UDim2.fromScale(1, 1)
composerBar.BackgroundColor3 = C.surface2
composerBar.BorderSizePixel = 0
composerBar.Parent = composerWrap
corner(composerBar, 16)

local composerStroke = Instance.new("UIStroke")
composerStroke.Color = C.border
composerStroke.Thickness = 1
composerStroke.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
composerStroke.Parent = composerBar

local composer = Instance.new("TextBox")
composer.BackgroundTransparency = 1
composer.Position = UDim2.new(0, 14, 0, 10)
composer.Size = UDim2.new(1, -28, 1, -48)
composer.TextColor3 = C.text
composer.PlaceholderText = "Ask Mango to build, fix, or explain..."
composer.PlaceholderColor3 = C.dim
composer.Text = ""
composer.TextXAlignment = Enum.TextXAlignment.Left
composer.TextYAlignment = Enum.TextYAlignment.Top
composer.ClearTextOnFocus = false
composer.MultiLine = true
composer.TextWrapped = true
composer.Font = Enum.Font.Gotham
composer.TextSize = 14
composer.Parent = composerBar

local footer = Instance.new("Frame")
footer.AnchorPoint = Vector2.new(0, 1)
footer.Position = UDim2.new(0, 8, 1, -8)
footer.Size = UDim2.new(1, -16, 0, 32)
footer.BackgroundTransparency = 1
footer.Parent = composerBar

local plusBtn = Instance.new("TextButton")
plusBtn.Size = UDim2.fromOffset(28, 28)
plusBtn.Position = UDim2.new(0, 0, 0.5, -14)
plusBtn.BackgroundTransparency = 1
plusBtn.Text = "+"
plusBtn.Font = Enum.Font.Gotham
plusBtn.TextSize = 20
plusBtn.TextColor3 = C.dim
plusBtn.AutoButtonColor = true
plusBtn.Parent = footer

-- Thinking strength chip (opens slider popup)
local THINK_LEVELS = {
	{ id = "off", label = "Off", desc = "Just go" },
	{ id = "think", label = "Think", desc = "A beat longer" },
	{ id = "deep", label = "Deep", desc = "Take the long way" },
	{ id = "max", label = "Max", desc = "Leave no stone" },
}

local function thinkingIndex(id)
	for i, row in ipairs(THINK_LEVELS) do
		if row.id == id then
			return i
		end
	end
	return 1
end

local function thinkingMeta(id)
	return THINK_LEVELS[thinkingIndex(id)]
end

-- Normalize persisted value
do
	local ok = false
	for _, row in ipairs(THINK_LEVELS) do
		if row.id == state.thinkingLevel then
			ok = true
			break
		end
	end
	if not ok then
		state.thinkingLevel = "off"
	end
end

local thinkChip = Instance.new("TextButton")
thinkChip.Position = UDim2.new(0, 30, 0.5, -14)
thinkChip.Size = UDim2.fromOffset(28, 28)
thinkChip.BackgroundTransparency = 1
thinkChip.Text = "◈"
thinkChip.Font = Enum.Font.Gotham
thinkChip.TextSize = 14
thinkChip.TextColor3 = C.dim
thinkChip.AutoButtonColor = true
thinkChip.Parent = footer

local function refreshThinkChip()
	local on = state.thinkingLevel ~= "off"
	thinkChip.TextColor3 = on and C.accent or C.dim
	local meta = thinkingMeta(state.thinkingLevel)
	thinkChip.Text = on and "◆" or "◇"
end
refreshThinkChip()

-- Model picker trigger (screenshot: logo + label + chevron)
local modelChip = Instance.new("TextButton")
modelChip.Position = UDim2.new(0, 60, 0.5, -14)
modelChip.Size = UDim2.fromOffset(148, 28)
modelChip.BackgroundTransparency = 1
modelChip.Text = ""
modelChip.AutoButtonColor = false
modelChip.Parent = footer

local mangoMark = Instance.new("Frame")
mangoMark.Size = UDim2.fromOffset(16, 16)
mangoMark.Position = UDim2.new(0, 2, 0.5, -8)
mangoMark.BackgroundColor3 = C.accent
mangoMark.BorderSizePixel = 0
mangoMark.Parent = modelChip
corner(mangoMark, 4)

local mangoMarkLetter = Instance.new("TextLabel")
mangoMarkLetter.BackgroundTransparency = 1
mangoMarkLetter.Size = UDim2.fromScale(1, 1)
mangoMarkLetter.Font = Enum.Font.GothamBold
mangoMarkLetter.TextSize = 10
mangoMarkLetter.TextColor3 = C.accentOn
mangoMarkLetter.Text = "M"
mangoMarkLetter.Parent = mangoMark

local modelLabel = Instance.new("TextLabel")
modelLabel.BackgroundTransparency = 1
modelLabel.Position = UDim2.new(0, 22, 0, 0)
modelLabel.Size = UDim2.new(1, -36, 1, 0)
modelLabel.Font = Enum.Font.Gotham
modelLabel.TextSize = 12
modelLabel.TextXAlignment = Enum.TextXAlignment.Left
modelLabel.TextColor3 = C.muted
modelLabel.Text = "No model"
modelLabel.Parent = modelChip

local modelChevron = Instance.new("TextLabel")
modelChevron.BackgroundTransparency = 1
modelChevron.AnchorPoint = Vector2.new(1, 0)
modelChevron.Position = UDim2.new(1, 0, 0, 0)
modelChevron.Size = UDim2.fromOffset(14, 28)
modelChevron.Font = Enum.Font.Gotham
modelChevron.TextSize = 10
modelChevron.TextColor3 = C.dim
modelChevron.Text = "▾"
modelChevron.Parent = modelChip

-- Dropdown menu (above composer)
local modelMenu = Instance.new("ScrollingFrame")
modelMenu.Visible = false
modelMenu.AnchorPoint = Vector2.new(0, 1)
modelMenu.Position = UDim2.new(0, 12, 1, -128)
modelMenu.Size = UDim2.new(1, -24, 0, 180)
modelMenu.BackgroundColor3 = C.surface3
modelMenu.BorderSizePixel = 0
modelMenu.ScrollBarThickness = 4
modelMenu.ZIndex = 20
modelMenu.CanvasSize = UDim2.new(0, 0, 0, 0)
modelMenu.AutomaticCanvasSize = Enum.AutomaticSize.Y
modelMenu.Parent = root
corner(modelMenu, 12)
local modelMenuStroke = Instance.new("UIStroke")
modelMenuStroke.Color = C.border
modelMenuStroke.Thickness = 1
modelMenuStroke.Parent = modelMenu
pad(modelMenu, 6, 6, 6, 6)

local modelMenuLayout = Instance.new("UIListLayout")
modelMenuLayout.Padding = UDim.new(0, 2)
modelMenuLayout.SortOrder = Enum.SortOrder.LayoutOrder
modelMenuLayout.Parent = modelMenu

local offlineHint = Instance.new("TextLabel")
offlineHint.BackgroundTransparency = 1
offlineHint.Position = UDim2.new(0, 214, 0, 0)
offlineHint.Size = UDim2.new(1, -300, 1, 0)
offlineHint.Font = Enum.Font.Gotham
offlineHint.TextSize = 11
offlineHint.TextXAlignment = Enum.TextXAlignment.Left
offlineHint.TextYAlignment = Enum.TextYAlignment.Center
offlineHint.TextColor3 = C.warn
offlineHint.Text = ""
offlineHint.Parent = footer

-- Thinking slider popup
local thinkPopup = Instance.new("Frame")
thinkPopup.Visible = false
thinkPopup.AnchorPoint = Vector2.new(0, 1)
thinkPopup.Position = UDim2.new(0, 12, 1, -128)
thinkPopup.Size = UDim2.fromOffset(248, 118)
thinkPopup.BackgroundColor3 = C.surface2
thinkPopup.BorderSizePixel = 0
thinkPopup.ZIndex = 25
thinkPopup.Parent = root
corner(thinkPopup, 14)
local thinkPopupStroke = Instance.new("UIStroke")
thinkPopupStroke.Color = C.border
thinkPopupStroke.Thickness = 1
thinkPopupStroke.Parent = thinkPopup
pad(thinkPopup, 12, 14, 12, 14)

local thinkTitle = Instance.new("TextLabel")
thinkTitle.BackgroundTransparency = 1
thinkTitle.Size = UDim2.new(1, 0, 0, 16)
thinkTitle.Font = Enum.Font.GothamBold
thinkTitle.TextSize = 12
thinkTitle.TextXAlignment = Enum.TextXAlignment.Left
thinkTitle.TextColor3 = C.text
thinkTitle.Text = "Thinking · Off"
thinkTitle.ZIndex = 26
thinkTitle.Parent = thinkPopup

local thinkDesc = Instance.new("TextLabel")
thinkDesc.BackgroundTransparency = 1
thinkDesc.Position = UDim2.new(0, 0, 0, 16)
thinkDesc.Size = UDim2.new(1, 0, 0, 16)
thinkDesc.Font = Enum.Font.Gotham
thinkDesc.TextSize = 11
thinkDesc.TextXAlignment = Enum.TextXAlignment.Left
thinkDesc.TextColor3 = C.dim
thinkDesc.Text = "Just go"
thinkDesc.ZIndex = 26
thinkDesc.Parent = thinkPopup

local trackWrap = Instance.new("TextButton")
trackWrap.BackgroundTransparency = 1
trackWrap.Position = UDim2.new(0, 0, 0, 42)
trackWrap.Size = UDim2.new(1, 0, 0, 28)
trackWrap.Text = ""
trackWrap.AutoButtonColor = false
trackWrap.ZIndex = 26
trackWrap.Parent = thinkPopup

local track = Instance.new("Frame")
track.AnchorPoint = Vector2.new(0, 0.5)
track.Position = UDim2.new(0, 0, 0.5, 0)
track.Size = UDim2.new(1, 0, 0, 12)
track.BorderSizePixel = 0
track.BackgroundColor3 = C.accent
track.ZIndex = 26
track.Parent = trackWrap
corner(track, 6)

local trackGrad = Instance.new("UIGradient")
trackGrad.Color = ColorSequence.new({
	ColorSequenceKeypoint.new(0, Color3.fromRGB(26, 18, 12)),
	ColorSequenceKeypoint.new(0.4, Color3.fromRGB(61, 42, 24)),
	ColorSequenceKeypoint.new(0.72, Color3.fromRGB(168, 106, 40)),
	ColorSequenceKeypoint.new(1, C.accent),
})
trackGrad.Parent = track

local trackDash = Instance.new("Frame")
trackDash.AnchorPoint = Vector2.new(0, 0.5)
trackDash.Position = UDim2.new(0, 8, 0.5, 0)
trackDash.Size = UDim2.new(1, -16, 0, 1)
trackDash.BackgroundColor3 = Color3.fromRGB(12, 10, 8)
trackDash.BackgroundTransparency = 0.35
trackDash.BorderSizePixel = 0
trackDash.ZIndex = 27
trackDash.Parent = track

-- Approximate dashed look with short ticks
for i = 0, 11 do
	local tick = Instance.new("Frame")
	tick.Size = UDim2.new(0, 4, 1, 0)
	tick.Position = UDim2.new(i / 11, 0, 0, 0)
	tick.BackgroundColor3 = Color3.fromRGB(12, 10, 8)
	tick.BackgroundTransparency = (i % 2 == 0) and 0.25 or 1
	tick.BorderSizePixel = 0
	tick.ZIndex = 28
	tick.Parent = trackDash
end

local knob = Instance.new("Frame")
knob.AnchorPoint = Vector2.new(0.5, 0.5)
knob.Position = UDim2.new(0, 0, 0.5, 0)
knob.Size = UDim2.fromOffset(18, 18)
knob.BackgroundColor3 = C.accent
knob.BorderSizePixel = 0
knob.ZIndex = 29
knob.Parent = trackWrap
corner(knob, 9)
local knobStroke = Instance.new("UIStroke")
knobStroke.Color = Color3.fromRGB(240, 192, 120)
knobStroke.Thickness = 2
knobStroke.Parent = knob

local labelRow = Instance.new("Frame")
labelRow.BackgroundTransparency = 1
labelRow.Position = UDim2.new(0, 0, 0, 74)
labelRow.Size = UDim2.new(1, 0, 0, 20)
labelRow.ZIndex = 26
labelRow.Parent = thinkPopup

local labelButtons = {}
for i, row in ipairs(THINK_LEVELS) do
	local btn = Instance.new("TextButton")
	btn.Size = UDim2.new(0.25, -2, 1, 0)
	btn.Position = UDim2.new((i - 1) * 0.25, 1, 0, 0)
	btn.BackgroundTransparency = 1
	btn.Font = Enum.Font.Gotham
	btn.TextSize = 10
	btn.TextColor3 = C.dim
	btn.Text = row.label
	btn.ZIndex = 27
	btn.AutoButtonColor = true
	btn.Parent = labelRow
	labelButtons[i] = btn
end

local function setThinkingLevel(id, persist)
	local meta = thinkingMeta(id)
	state.thinkingLevel = meta.id
	if persist ~= false then
		plugin:SetSetting("MangoThinkingLevel", state.thinkingLevel)
	end
	thinkTitle.Text = "Thinking · " .. meta.label
	thinkDesc.Text = meta.desc
	local idx = thinkingIndex(state.thinkingLevel)
	local t = (idx - 1) / math.max(1, #THINK_LEVELS - 1)
	knob.Position = UDim2.new(t, 0, 0.5, 0)
	local on = state.thinkingLevel ~= "off"
	knob.BackgroundColor3 = on and C.accent or Color3.fromRGB(26, 18, 8)
	knobStroke.Color = on and Color3.fromRGB(240, 192, 120) or C.accent
	for i, btn in ipairs(labelButtons) do
		btn.TextColor3 = (i == idx) and C.accent or C.dim
	end
	refreshThinkChip()
end
setThinkingLevel(state.thinkingLevel, false)

local function setThinkingOpen(open)
	state.thinkingOpen = open and true or false
	thinkPopup.Visible = state.thinkingOpen
	if open then
		state.pickerOpen = false
		modelMenu.Visible = false
		modelChevron.Text = "▾"
	end
end

local function levelFromX(x)
	local abs = track.AbsolutePosition.X
	local w = track.AbsoluteSize.X
	if w <= 0 then
		return state.thinkingLevel
	end
	local t = math.clamp((x - abs) / w, 0, 1)
	local idx = math.clamp(math.floor(t * (#THINK_LEVELS - 1) + 0.5) + 1, 1, #THINK_LEVELS)
	return THINK_LEVELS[idx].id
end

local draggingThink = false
trackWrap.InputBegan:Connect(function(input)
	if input.UserInputType == Enum.UserInputType.MouseButton1 or input.UserInputType == Enum.UserInputType.Touch then
		draggingThink = true
		setThinkingLevel(levelFromX(input.Position.X), true)
	end
end)
trackWrap.InputEnded:Connect(function(input)
	if input.UserInputType == Enum.UserInputType.MouseButton1 or input.UserInputType == Enum.UserInputType.Touch then
		draggingThink = false
	end
end)
trackWrap.InputChanged:Connect(function(input)
	if draggingThink and (input.UserInputType == Enum.UserInputType.MouseMovement or input.UserInputType == Enum.UserInputType.Touch) then
		setThinkingLevel(levelFromX(input.Position.X), true)
	end
end)

for i, btn in ipairs(labelButtons) do
	btn.MouseButton1Click:Connect(function()
		setThinkingLevel(THINK_LEVELS[i].id, true)
	end)
end

local micBtn = Instance.new("TextButton")
micBtn.AnchorPoint = Vector2.new(1, 0.5)
micBtn.Position = UDim2.new(1, -40, 0.5, 0)
micBtn.Size = UDim2.fromOffset(28, 28)
micBtn.BackgroundTransparency = 1
micBtn.Text = "🎙"
micBtn.Font = Enum.Font.Gotham
micBtn.TextSize = 14
micBtn.TextColor3 = C.dim
micBtn.AutoButtonColor = true
micBtn.Parent = footer

local cancelBtn = Instance.new("TextButton")
cancelBtn.AnchorPoint = Vector2.new(1, 0.5)
cancelBtn.Position = UDim2.new(1, -40, 0.5, 0)
cancelBtn.Size = UDim2.fromOffset(28, 28)
cancelBtn.BackgroundColor3 = C.surface3
cancelBtn.Text = "■"
cancelBtn.Font = Enum.Font.GothamBold
cancelBtn.TextSize = 10
cancelBtn.TextColor3 = C.danger
cancelBtn.Visible = false
cancelBtn.AutoButtonColor = true
cancelBtn.ZIndex = 2
cancelBtn.Parent = footer
corner(cancelBtn, 14)

local sendBtn = Instance.new("TextButton")
sendBtn.AnchorPoint = Vector2.new(1, 0.5)
sendBtn.Position = UDim2.new(1, 0, 0.5, 0)
sendBtn.Size = UDim2.fromOffset(32, 32)
sendBtn.BackgroundColor3 = C.accent
sendBtn.Text = "↑"
sendBtn.Font = Enum.Font.GothamBold
sendBtn.TextSize = 16
sendBtn.TextColor3 = C.accentOn
sendBtn.AutoButtonColor = true
sendBtn.Parent = footer
corner(sendBtn, 16)

local function setModelLabel(label)
	state.modelLabel = label or "No model"
	modelLabel.Text = state.modelLabel
end

local function clearModelMenu()
	for _, child in ipairs(modelMenu:GetChildren()) do
		if child:IsA("TextButton") then
			child:Destroy()
		end
	end
end

local function setPickerOpen(open)
	state.pickerOpen = open
	modelMenu.Visible = open
	modelChevron.Text = open and "▴" or "▾"
	if open then
		setThinkingOpen(false)
	end
end

local function selectModel(path, label)
	if not path or path == "" then
		return
	end
	setPickerOpen(false)
	if path == state.modelPath then
		return
	end
	appendLine("Switching model → " .. tostring(label), C.dim)
	local ok, data = httpJson("POST", "/v1/settings", { model_path = path })
	if not ok then
		appendLine("Model switch failed: " .. tostring(data), C.danger)
		return
	end
	state.modelPath = path
	setModelLabel(label or (data and data.model_name) or path)
	appendLine("Model set: " .. state.modelLabel, C.ok)
end

local function rebuildModelMenu()
	clearModelMenu()
	if #state.models == 0 then
		local empty = Instance.new("TextLabel")
		empty.BackgroundTransparency = 1
		empty.Size = UDim2.new(1, 0, 0, 28)
		empty.Font = Enum.Font.Gotham
		empty.TextSize = 12
		empty.TextColor3 = C.dim
		empty.Text = "No GGUF models found"
		empty.ZIndex = 21
		empty.Parent = modelMenu
		return
	end
	for i, m in ipairs(state.models) do
		local row = Instance.new("TextButton")
		row.Size = UDim2.new(1, 0, 0, 30)
		row.BackgroundColor3 = (m.path == state.modelPath) and Color3.fromRGB(48, 40, 28) or C.surface3
		row.BorderSizePixel = 0
		row.AutoButtonColor = true
		row.Text = ""
		row.LayoutOrder = i
		row.ZIndex = 21
		row.Parent = modelMenu
		corner(row, 8)

		local mark = Instance.new("Frame")
		mark.Size = UDim2.fromOffset(14, 14)
		mark.Position = UDim2.new(0, 8, 0.5, -7)
		mark.BackgroundColor3 = C.accent
		mark.BorderSizePixel = 0
		mark.ZIndex = 22
		mark.Parent = row
		corner(mark, 3)

		local lbl = Instance.new("TextLabel")
		lbl.BackgroundTransparency = 1
		lbl.Position = UDim2.new(0, 28, 0, 0)
		lbl.Size = UDim2.new(1, -36, 1, 0)
		lbl.Font = Enum.Font.Gotham
		lbl.TextSize = 12
		lbl.TextXAlignment = Enum.TextXAlignment.Left
		lbl.TextColor3 = C.text
		lbl.Text = m.label or m.path
		lbl.ZIndex = 22
		lbl.Parent = row

		local path, label = m.path, m.label
		row.MouseButton1Click:Connect(function()
			selectModel(path, label)
		end)
	end
end

local function refreshModels()
	local ok, data = httpJson("GET", "/v1/models")
	if not ok or type(data) ~= "table" then
		return
	end
	state.models = data.models or {}
	local current = data.current or ""
	if current ~= "" then
		state.modelPath = current
		local found = nil
		for _, m in ipairs(state.models) do
			if m.path == current then
				found = m.label
				break
			end
		end
		setModelLabel(found or current:match("([^/\\]+)%.gguf$") or current)
	elseif #state.models > 0 then
		setModelLabel(state.models[1].label)
		state.modelPath = state.models[1].path
	end
	if state.pickerOpen then
		rebuildModelMenu()
	end
end

local function setBusyUi(busy)
	state.busy = busy
	cancelBtn.Visible = busy
	micBtn.Visible = not busy
	sendBtn.Visible = not busy
	if busy then
		sendBtn.BackgroundColor3 = C.dim
	else
		sendBtn.BackgroundColor3 = C.accent
	end
end

local function appendLine(text, color)
	local line = Instance.new("TextLabel")
	line.BackgroundTransparency = 1
	line.Size = UDim2.new(1, -4, 0, 0)
	line.AutomaticSize = Enum.AutomaticSize.Y
	line.Font = Enum.Font.Gotham
	line.TextSize = 13
	line.TextXAlignment = Enum.TextXAlignment.Left
	line.TextYAlignment = Enum.TextYAlignment.Top
	line.TextWrapped = true
	line.TextColor3 = color or C.muted
	line.Text = text
	line.Parent = transcript
	task.defer(function()
		transcript.CanvasPosition = Vector2.new(0, math.max(0, transcriptLayout.AbsoluteContentSize.Y))
	end)
end

local function setStatus(text, color)
	statusLabel.Text = text
	statusLabel.TextColor3 = color or C.dim
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
						setBusyUi(false)
						setStatus(
							state.online and "online" or "offline",
							state.online and C.ok or C.warn
						)
					elseif name == "agent.started" then
						setBusyUi(true)
						setStatus("running…", C.accent)
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
		local sid = data.sidecar and "sidecar" or "no sidecar"
		local model = data.model_loaded and " · model" or ""
		setStatus(("%s%s"):format(sid, model), C.ok)
		composerStroke.Color = C.border
		return true
	end
	state.online = false
	setStatus("offline", C.warn)
	offlineHint.Text = "Start host"
	composerStroke.Color = C.warn
	return false
end

local function sendGoal()
	local goal = composer.Text
	if not goal or goal:match("^%s*$") then
		return
	end
	if state.busy then
		return
	end
	if not refreshHealth() then
		appendLine("Host offline — run MangoStudio.cmd", C.warn)
		return
	end
	appendLine("You: " .. goal, C.text)
	composer.Text = ""
	setBusyUi(true)
	local ok, data = httpJson("POST", "/v1/run", {
		session_id = state.sessionId,
		goal = goal,
		mode = "roblox",
		thinking_level = state.thinkingLevel or "off",
		selection = selectionContext(),
	})
	if not ok then
		setBusyUi(false)
		appendLine("Run failed: " .. tostring(data), C.danger)
		return
	end
	setStatus("running…", C.accent)
end

sendBtn.MouseButton1Click:Connect(sendGoal)
composer.FocusLost:Connect(function(enter)
	if enter and composer.Text ~= "" and not state.busy then
		-- FocusLost enterPressed varies by Studio version
	end
end)

cancelBtn.MouseButton1Click:Connect(function()
	httpJson("POST", "/v1/cancel", {})
	setBusyUi(false)
	appendLine("(cancelled)", C.warn)
end)

plusBtn.MouseButton1Click:Connect(function()
	local sel = selectionContext()
	if sel then
		appendLine("Context: " .. sel:gsub("\n", ", "), C.dim)
	else
		appendLine("Select instances in Explorer to attach as context.", C.dim)
	end
end)

modelChip.MouseButton1Click:Connect(function()
	if state.busy then
		return
	end
	if not state.online then
		appendLine("Host offline — start MangoStudio.cmd first", C.warn)
		return
	end
	setThinkingOpen(false)
	if state.pickerOpen then
		setPickerOpen(false)
		return
	end
	refreshModels()
	rebuildModelMenu()
	setPickerOpen(true)
end)

thinkChip.MouseButton1Click:Connect(function()
	if state.busy then
		return
	end
	setPickerOpen(false)
	setThinkingOpen(not state.thinkingOpen)
end)

micBtn.MouseButton1Click:Connect(function()
	appendLine("Voice input isn’t available in the Studio plugin yet.", C.dim)
end)

button.Click:Connect(function()
	widget.Enabled = not widget.Enabled
	if widget.Enabled then
		refreshHealth()
		refreshModels()
		pollStudioLoop()
		pollEventsLoop()
	else
		setPickerOpen(false)
		setThinkingOpen(false)
	end
end)

task.spawn(function()
	while true do
		if widget.Enabled then
			refreshHealth()
		end
		task.wait(5)
	end
end)

appendLine("Mango ready. Start the host, pick a model, then ask it to build, fix, or explain.", C.dim)
