-- Usage: osascript enable_in_safari.applescript <ui-dump-path> <extension display name>...
-- Opens Safari Settings > Extensions and ticks every checkbox whose row mentions one of the names.
-- Writes a dump of the checkboxes/labels it saw so the selectors can be fixed when Safari's UI changes.
on run argv
	set dumpPath to item 1 of argv
	set wanted to rest of argv
	set dump to ""
	tell application "Safari" to activate
	delay 3
	tell application "System Events"
		tell process "Safari"
			set frontmost to true
			keystroke "," using command down
			delay 3
			set w to front window
			try
				click button "Extensions" of toolbar 1 of w
			on error
				click (first UI element of toolbar 1 of w whose name is "Extensions")
			end try
			delay 3
			set els to entire contents of w
			repeat with e in els
				try
					set r to role of e
					if r is "AXCheckBox" or r is "AXStaticText" then
						set t to ""
						try
							set t to name of e
						end try
						if t is missing value or t is "" then
							try
								set t to value of attribute "AXTitle" of e
							end try
						end if
						if r is "AXStaticText" then
							try
								set t to value of e
							end try
						end if
						set dump to dump & r & " | " & (t as text) & linefeed
						if r is "AXCheckBox" then
							-- match on checkbox title, or on any static text in the same row
							set rowText to (t as text)
							try
								set p to parent of e
								repeat with s in (static texts of p)
									set rowText to rowText & " " & (value of s as text)
								end repeat
							end try
							repeat with n in wanted
								if rowText contains (n as text) then
									if (value of e) is 0 then
										click e
										delay 1
										set dump to dump & "  -> ENABLED " & (n as text) & linefeed
									else
										set dump to dump & "  -> already on " & (n as text) & linefeed
									end if
									exit repeat
								end if
							end repeat
						end if
					end if
				end try
			end repeat
			keystroke "w" using command down
		end tell
	end tell
	do shell script "cat > " & quoted form of dumpPath & " <<'__EOF__'" & linefeed & dump & linefeed & "__EOF__"
end run
