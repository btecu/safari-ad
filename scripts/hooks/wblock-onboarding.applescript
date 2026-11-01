-- Click through wBlock's first-run "Set up wBlock" sheet (wBlock/OnboardingView.swift):
--   welcome [Get Started] -> protection -> regional -> userscripts -> sync [Next] -> setup [Apply & Finish]
-- Defaults are kept on every step ("Recommended" protection, system language). The primary button is
-- the sheet's default action, so pressing Return advances even when the button can't be found in the
-- accessibility tree or is off-screen (the sheet is taller than the runner's display).
-- On the setup step, "Apply & Finish" stays disabled until the two "I've enabled the extensions"
-- toggles are on; wBlock only lets them stick if Safari reports the blockers enabled, so
-- enable_in_safari.py must run first.
-- Usage: osascript wblock-onboarding.applescript <diag-dir>
on run argv
	set diagDir to item 1 of argv
	set log_ to ""
	tell application "wBlock" to activate
	delay 5
	repeat with i from 1 to 12
		set ui to my describeUI()
		do shell script "cat > " & quoted form of (diagDir & "/wblock-ui-step-" & i & ".txt") & " <<'__EOF__'" & linefeed & ui & linefeed & "__EOF__"
		-- Done when the main window is readable but the onboarding sheet isn't there. (If the
		-- accessibility tree is empty we can't tell, so keep pressing Return instead of giving up.)
		if ui does not contain "Set up wBlock" and ui contains "Filters" then
			set log_ to log_ & "step " & i & ": onboarding sheet gone; done" & linefeed
			exit repeat
		end if
		set stepAction to "Return"
		tell application "System Events"
			tell process "wBlock"
				set frontmost to true
				if ui contains "Apply & Finish" then
					-- tick the "enabled in Safari" toggles (checkboxes or switches that are off)
					repeat with w in windows
						repeat with e in (entire contents of w)
							try
								if role of e is in {"AXCheckBox", "AXSwitch"} and (value of e as integer) is 0 then
									perform action "AXPress" of e
									delay 3
									set log_ to log_ & "  toggled " & (description of e as text) & " -> " & (value of e as text) & linefeed
								end if
							end try
						end repeat
					end repeat
					delay 2
					set stepAction to "Apply & Finish (Return)"
				end if
				if ui contains "Start Fresh" then
					-- iCloud "existing configuration" alert
					repeat with w in windows
						repeat with e in (entire contents of w)
							try
								if role of e is "AXButton" and my label(e) contains "Start Fresh" then perform action "AXPress" of e
							end try
						end repeat
					end repeat
					set stepAction to "Start Fresh"
				else
					key code 36 -- Return: the sheet's default action (Get Started / Next / Apply & Finish)
				end if
			end tell
		end tell
		set log_ to log_ & "step " & i & ": " & stepAction & linefeed
		do shell script "screencapture -x " & quoted form of (diagDir & "/wblock-onboarding-" & i & ".png")
		delay 4
	end repeat
	return log_
end run

-- Best available label for an element: title, description, or value.
on label(e)
	set t to ""
	tell application "System Events"
		try
			set t to t & (name of e as text) & " "
		end try
		try
			set t to t & (description of e as text) & " "
		end try
		try
			set t to t & (value of e as text)
		end try
	end tell
	return t
end label

-- Flat dump of every UI element (role | labels) in all wBlock windows, for diagnostics and step detection.
on describeUI()
	set out to ""
	tell application "System Events"
		tell process "wBlock"
			repeat with w in windows
				set out to out & "WINDOW " & (name of w as text) & linefeed
				repeat with e in (entire contents of w)
					try
						set out to out & (role of e) & " | " & my label(e) & linefeed
					end try
				end repeat
			end repeat
		end tell
	end tell
	return out
end describeUI
