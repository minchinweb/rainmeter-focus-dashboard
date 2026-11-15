-- Legend numbers for the CPURecorder skin: how many cores are pegged, which core
-- is the hottest, and how hot.
--
-- It reads each core's pen position (MeasureCore<i>x, 0..1, a damped spring), not
-- the raw load, so a one-frame flicker does not count as pegged. Update() runs
-- once a second.

local cores, peg_at = 0, 90
local pegged, hottest, hottest_pct = 0, 0, 0

function Initialize()
    cores = tonumber(SKIN:GetVariable('Cores'))
    peg_at = tonumber(SKIN:GetVariable('PegAt'))
end

function Update()
    local best, who, count = -1, 0, 0
    for i = 1, cores do
        local pct = SKIN:GetMeasure('MeasureCore' .. i .. 'x'):GetValue() * 100
        if pct > best then
            best, who = pct, i
        end
        if pct >= peg_at then
            count = count + 1
        end
    end
    pegged, hottest, hottest_pct = count, who, math.floor(best + 0.5)
    return best
end

function Pegged() return pegged end
function Hottest() return hottest end
function HottestPct() return hottest_pct end
