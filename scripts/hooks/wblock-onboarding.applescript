-- Click through wBlock's first-run "Set up wBlock" sheet (wBlock/OnboardingView.swift):
--   welcome [Get Started] -> protection -> regional -> userscripts -> sync [Next] -> setup [Apply & Finish]
-- Defaults are kept on every step ("Recommended" protection, system language). On the setup step,
-- "Apply & Finish" stays disabled until the two "I've enabled the extensions" toggles are on; wBlock
-- only lets them stick if Safari reports the blockers enabled, so enable_in_safari.py must run first.
-- Usage: osascript wblock-onboarding.applescript <screenshot-dir>
on run argv
	set shotDir to item 1 of argv
	set log_ to ""
	tell application "wBlock" to activate
	delay 5
	repeat with i from 1 to 12
		set clicked to ""
		tell application "System Events"
			tell process "wBlock"
				set frontmost to true
				set els to entire contents of front window
				-- iCloud "existing configuration" alert, if it ever appears
				repeat with e in els
					try
						if role of e is "AXButton" and name of e is "Start Fresh" then
							click e
							set clicked to "Start Fresh"
							exit repeat
						end if
					end try
				end repeat
				if clicked is "" then
					set target to missing value
					repeat with e in els
						try
							if role of e is "AXButton" and name of e is in {"Get Started", "Next", "Apply & Finish"} then
								set target to e
								exit repeat
							end if
						end try
					end repeat
					if target is missing value then
						set log_ to log_ & "step " & i & ": no onboarding button; done" & linefeed
						exit repeat
					end if
					if name of target is "Apply & Finish" then
						-- tick the "enabled in Safari" toggles
						repeat with e in els
							try
								if role of e is in {"AXCheckBox", "AXSwitch"} and (value of e as integer) is 0 then
									click e
									delay 3
									set log_ to log_ & "  ticked toggle, now " & (value of e as text) & linefeed
								end if
							end try
						end repeat
						delay 2
					end if
					set clicked to name of target
					click target
				end if
			end tell
		end tell
		set log_ to log_ & "step " & i & ": clicked " & clicked & linefeed
		do shell script "screencapture -x " & quoted form of (shotDir & "/wblock-onboarding-" & i & ".png")
		delay 3
	end repeat
	return log_
end run
