-- Legend numbers for the NetworkRecorder skin: the download and upload rates, in
-- bits per second, as a short string (123.4 Mb/s).
--
-- NetIn and NetOut are bytes a second measured over each 125 ms update, which is
-- jumpy. Update() runs every update and keeps a moving average of each (about
-- half a second), and the skin reads Down() and Up() once a second.

local alpha = 0.2 -- share of each new reading in the average
local down, up = 0, 0

function Update()
    local d = SKIN:GetMeasure('MeasureNetIn'):GetValue() * 8
    local u = SKIN:GetMeasure('MeasureNetOut'):GetValue() * 8
    down = down + alpha * (d - down)
    up = up + alpha * (u - up)
    return down
end

local function format(bits)
    if bits >= 1e9 then
        return string.format('%.2f Gb/s', bits / 1e9)
    elseif bits >= 1e6 then
        return string.format('%.1f Mb/s', bits / 1e6)
    elseif bits >= 1e3 then
        return string.format('%.0f kb/s', bits / 1e3)
    end
    return string.format('%.0f b/s', bits)
end

function Down() return format(down) end
function Up() return format(up) end
