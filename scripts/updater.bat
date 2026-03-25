
@echo off

rem Wait for a period of time (e.g., 20 seconds)
timeout /t 20

rem Replace the original executable with the updated one
set "tempExePath=.\temp\GMonster.exe"  rem Replace with the actual path of the updated executable
set "originalExePath=.\GMonster.exe"  rem Replace with the actual path of the original executable
copy /y "%tempExePath%" "%originalExePath%"

rem Execute the updated version of the application
start "" "%originalExePath%"

set "tempExePath=.\temp\WUM.exe"  rem Replace with the actual path of the updated executable
set "originalExePath=.\WUM.exe"  rem Replace with the actual path of the original executable
copy /y "%tempExePath%" "%originalExePath%"
            
            