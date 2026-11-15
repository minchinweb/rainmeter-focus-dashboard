-- Paper clock for the SystemRecorder and CPURecorder skins.
--
-- The paper moves one pixel per sample, and a heavy rule is printed every
-- TickEvery pixels (= seconds). `count` is how many pixels the newest heavy
-- rule is from the pen. It starts from the wall clock, so the rules land on
-- multiples of TickEvery seconds (:00, :30), and it counts samples after that.
-- If the count drifts two or more seconds from the clock, it is set back.
--
-- Update() returns the count, which the skin uses to slide the paper.
-- Label(k) is the clock time of the k-th heavy rule from the pen (0 = newest),
-- as of the last sample.

local period, count, stamp

function Initialize()
    period = tonumber(SKIN:GetVariable('TickEvery'))
    stamp = os.time()
    count = (stamp - 1) % period -- Update() adds the first sample's pixel
end

function Update()
    local now = os.time()
    count = (count + 1) % period
    local half = math.floor(period / 2)
    local drift = ((now % period) - count + half) % period - half
    if math.abs(drift) >= 2 then
        count = now % period
    end
    stamp = now
    return count
end

function Label(k)
    -- no leading zero on the hour: 1:25:30, 13:25:30
    return (os.date('%H:%M:%S', stamp - count - k * period):gsub('^0', ''))
end
