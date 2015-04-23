# $Id: ws28xx.py 2775 2014-12-03 20:19:47Z mwall $
# Copyright 2013 Matthew Wall
# See the file LICENSE.txt for your full rights.
#
# Thanks to Eddie De Pieri for the first Python implementation for WS-28xx.
# Eddie did the difficult work of decompiling HeavyWeather then converting
# and reverse engineering into a functional Python implementation.  Eddie's
# work was based on reverse engineering of HeavyWeather 2800 v 1.54
#
# Thanks to Lucas Heijst for enumerating the console message types and for
# debugging the transceiver/console communication timing issues.

"""Classes and functions for interfacing with WS-28xx weather stations.

LaCrosse makes a number of stations in the 28xx series, including:

  WS-2810, WS-2810U-IT
  WS-2811, WS-2811SAL-IT,  WS-2811BRN-IT,  WS-2811OAK-IT
  WS-2812, WS-2812U-IT
  WS-2813
  WS-2814, WS-2814U-IT
  WS-2815, WS-2815U-IT
  C86234

The station is also sold as the TFA Primus, TFA Opus, and TechnoLine.

HeavyWeather is the software provided by LaCrosse.

There are two versions of HeavyWeather for the WS-28xx series: 1.5.4 and 1.5.4b
Apparently there is a difference between TX59UN-1-IT and TX59U-IT models (this
identifier is printed on the thermo-hygro sensor).

   HeavyWeather Version    Firmware Version    Thermo-Hygro Model
   1.54                    333 or 332          TX59UN-1-IT
   1.54b                   288, 262, 222       TX59U-IT

HeavyWeather provides the following weather station settings:

  time display: 12|24 hour
  temperature display: C|F
  air pressure display: inhg|hpa
  wind speed display: m/s|knots|bft|km/h|mph
  rain display: mm|inch
  recording interval: 1m
  keep weather station in hi-speed communication mode: true/false

According to the HeavyWeatherPro User Manual (1.54, rev2), "Hi speed mode wears
down batteries on your display much faster, and similarly consumes more power
on the PC.  We do not believe most users need to enable this setting.  It was
provided at the request of users who prefer ultra-frequent uploads."

The HeavyWeatherPro 'CurrentWeather' view is updated as data arrive from the
console.  The console sends current weather data approximately every 13
seconds.

Historical data are updated less frequently - every 2 hours in the default
HeavyWeatherPro configuration.

According to the User Manual, "The 2800 series weather station uses the
'original' wind chill calculation rather than the 2001 'North American'
formula because the original formula is international."

Apparently the station console determines when data will be sent, and, once
paired, the transceiver is always listening.  The station console sends a
broadcast on the hour.  If the transceiver responds, the station console may
continue to broadcast data, depending on the transceiver response and the
timing of the transceiver response.

According to the C86234 Operations Manual (Revision 7):
 - Temperature and humidity data are sent to the console every 13 seconds.
 - Wind data are sent to the temperature/humidity sensor every 17 seconds.
 - Rain data are sent to the temperature/humidity sensor every 19 seconds.
 - Air pressure is measured every 15 seconds.

Each tip of the rain bucket is 0.26 mm of rain.

The following information was obtained by logging messages from the ws28xx.py
driver in weewx and by capturing USB messages between Heavy Weather Pro for
ws2800 and the TFA Primus Weather Station via windows program USB sniffer
busdog64_v0.2.1.

Pairing

The transceiver must be paired with a console before it can receive data.  Each
frame sent by the console includes the device identifier of the transceiver
with which it is paired.

Synchronizing

When the console and transceiver stop communicating, they can be synchronized
by one of the following methods:

- Push the SET button on the console
- Wait till the next full hour when the console sends a clock message

In each case a Request Time message is received by the transceiver from the
console. The 'Send Time to WS' message should be sent within ms (10 ms
typical). The transceiver should handle the 'Time SET' message then send a
'Time/Config written' message about 85 ms after the 'Send Time to WS' message.
When complete, the console and transceiver will have been synchronized.

Timing

Current Weather messages, History messages, getConfig/setConfig messages, and
setTime messages each have their own timing.  Missed History messages - as a
result of bad timing - result in console and transceiver becoming out of synch.

Current Weather

The console periodically sends Current Weather messages, each with the latest
values from the sensors.  The CommModeInterval determines how often the console
will send Current Weather messages.

History

The console records data periodically at an interval defined by the
HistoryInterval parameter.  The factory default setting is 2 hours.
Each history record contains a timestamp.  Timestamps use the time from the
console clock.  The console can record up to 1797 history records.

Reading 1795 history records took about 110 minutes on a raspberry pi, for
an average of 3.6 seconds per history record.

Reading 1795 history records took 65 minutes on a synology ds209+ii, for
an average of 2.2 seconds per history record.

Reading 1750 history records took 19 minutes using HeavyWeatherPro on a
Windows 7 64-bit laptop.

Message Types

The first byte of a message determines the message type.

ID   Type               length

01   ?                  0x0f  (15)
d0   SetRX              0x15  (21)
d1   SetTX              0x15  (21)
d5   SetFrame           0x111 (273)
d6   GetFrame           0x111 (273)
d7   SetState           0x15  (21)
d8   SetPreamblePattern 0x15  (21)
d9   Execute            0x0f  (15)
dc   ReadConfigFlash<   0x15  (21)
dd   ReadConfigFlash>   0x15  (21)
de   GetState           0x0a  (10)
f0   WriteReg           0x05  (5)

In the following sections, some messages are decomposed using the following
structure:

  start   position in message buffer
  hi-lo   data starts on first (hi) or second (lo) nibble
  chars   data length in characters (nibbles)
  rem     remark
  name    variable

-------------------------------------------------------------------------------
1. 01 message (15 bytes)

000:  01 15 00 0b 08 58 3f 53 00 00   00 00 ff 15 0b (detected via USB sniffer)
000:  01 15 00 57 01 92 3f 53 00 00   00 00 ff 15 0a (detected via USB sniffer)

00:    messageID
02-15: ??

-------------------------------------------------------------------------------
2. SetRX message (21 bytes)

000:  d0 00 00 00 00 00 00 00 00 00   00 00 00 00 00 00 00 00 00 00
020:  00 
  
00:    messageID
01-20: 00

-------------------------------------------------------------------------------
3. SetTX message (21 bytes)

000: d1 00 00 00 00 00 00 00 00 00   00 00 00 00 00 00 00 00 00 00
020: 00 
  
00:    messageID
01-20: 00

-------------------------------------------------------------------------------
4. SetFrame message (273 bytes)

Action:
00: rtGetHistory     - Ask for History message
01: rtSetTime        - Ask for Send Time to weather station message
02: rtSetConfig      - Ask for Send Config to weather station message
02: rtReqFirstConfig - Ask for Send (First) Config to weather station message
03: rtGetConfig      - Ask for Config message
05: rtGetCurrent     - Ask for Current Weather 
40: Send Config      - Send Config to WS
c0: Send Time        - Send Time to WS

000:  d5 00 09 DevID 00 CfgCS cIntThisAdr xx xx xx  rtGetHistory 
000:  d5 00 09 DevID 01 CfgCS cIntThisAdr xx xx xx  rtReqSetTime
000:  d5 00 09 f0 f0 02 CfgCS cIntThisAdr xx xx xx  rtReqFirstConfig
000:  d5 00 09 DevID 02 CfgCS cIntThisAdr xx xx xx  rtReqSetConfig
000:  d5 00 09 DevID 03 CfgCS cIntThisAdr xx xx xx  rtGetConfig
000:  d5 00 09 DevID 05 CfgCS cIntThisAdr xx xx xx  rtGetCurrent
000:  d5 00 0c DevID c0 CfgCS [TimeData . .. .. ..  Send Time
000:  d5 00 30 DevID 40 CfgCS [ConfigData .. .. ..  Send Config

All SetFrame messages:
00:    messageID
01:    00
02:    Message length (starting with next byte)
03-04: DeviceID           [DevID]
05:    Action
06-07: Config checksum    [CfgCS]

Additional bytes rtGetCurrent, rtGetHistory, rtSetTime messages:
08-09hi: ComInt             [cINT]    1.5 bytes (high byte first)
09lo-11: ThisHistoryAddress [ThisAdr] 2.5 bytes (high byte first)

Additional bytes Send Time message:
08:    seconds
09:    minutes
10:    hours
11hi:  DayOfWeek
11lo:  day_lo         (low byte)
12hi:  month_lo       (low byte)
12lo:  day_hi         (high byte)
13hi:  (year-2000)_lo (low byte)
13lo:  month_hi       (high byte)
14lo:  (year-2000)_hi (high byte)

-------------------------------------------------------------------------------
5. GetFrame message

Response type:
20: WS SetTime / SetConfig - Data written
40: GetConfig
60: Current Weather
80: Actual / Outstanding History
a1: Request First-Time Config
a2: Request SetConfig
a3: Request SetTime

000:  00 00 06 DevID 20 64 CfgCS xx xx xx xx xx xx xx xx xx  Time/Config written
000:  00 00 30 DevID 40 64 [ConfigData .. .. .. .. .. .. ..  GetConfig
000:  00 00 d7 DevID 60 64 CfgCS [CurData .. .. .. .. .. ..  Current Weather
000:  00 00 1e DevID 80 64 CfgCS 0LateAdr 0ThisAdr [HisData  Outstanding History
000:  00 00 1e DevID 80 64 CfgCS 0LateAdr 0ThisAdr [HisData  Actual History
000:  00 00 06 DevID a1 64 CfgCS xx xx xx xx xx xx xx xx xx  Request FirstConfig
000:  00 00 06 DevID a2 64 CfgCS xx xx xx xx xx xx xx xx xx  Request SetConfig
000:  00 00 06 DevID a3 64 CfgCS xx xx xx xx xx xx xx xx xx  Request SetTime

ReadConfig example:  
000: 01 2e 40 5f 36 53 02 00 00 00  00 81 00 04 10 00 82 00 04 20
020: 00 71 41 72 42 00 05 00 00 00  27 10 00 02 83 60 96 01 03 07
040: 21 04 01 00 00 00 CfgCS

WriteConfig example:
000: 01 2e 40 64 36 53 02 00 00 00  00 00 10 04 00 81 00 20 04 00
020: 82 41 71 42 72 00 00 05 00 00  00 10 27 01 96 60 83 02 01 04
040: 21 07 03 10 00 00 CfgCS

00:    messageID
01:    00
02:    Message length (starting with next byte)
03-04: DeviceID [devID]
05hi:  responseType
06:    Quality (in steps of 5)

Additional byte GetFrame messages except Request SetConfig and Request SetTime:
05lo:  BatteryStat 8=WS bat low; 4=TMP bat low; 2=RAIN bat low; 1=WIND bat low

Additional byte Request SetConfig and Request SetTime:
05lo:  RequestID

Additional bytes all GetFrame messages except ReadConfig and WriteConfig
07-08: Config checksum [CfgCS]

Additional bytes Outstanding History:
09lo-11: LatestHistoryAddress [LateAdr] 2.5 bytes (Latest to sent)
12lo-14: ThisHistoryAddress   [ThisAdr] 2.5 bytes (Outstanding)

Additional bytes Actual History:
09lo-11: LatestHistoryAddress [ThisAdr] 2.5 bytes (LatestHistoryAddress is the)
12lo-14: ThisHistoryAddress   [ThisAdr] 2.5 bytes (same as ThisHistoryAddress)

Additional bytes ReadConfig and WriteConfig
43-45: ResetMinMaxFlags (Output only; not included in checksum calculation)
46-47: Config checksum [CfgCS] (CheckSum = sum of bytes (00-42) + 7)

-------------------------------------------------------------------------------
6. SetState message

000:  d7 00 00 00 00 00 00 00 00 00 00 00 00 00 00

00:    messageID
01-14: 00

-------------------------------------------------------------------------------
7. SetPreamblePattern message

000:  d8 aa 00 00 00 00 00 00 00 00 00 00 00 00 00

00:    messageID
01:    ??
02-14: 00

-------------------------------------------------------------------------------
8. Execute message

000:  d9 05 00 00 00 00 00 00 00 00 00 00 00 00 00

00:    messageID
01:    ??
02-14: 00

-------------------------------------------------------------------------------
9. ReadConfigFlash in - receive data

000: dc 0a 01 f5 00 01 78 a0 01 02  0a 0c 0c 01 2e ff ff ff ff ff - freq correction
000: dc 0a 01 f9 01 02 0a 0c 0c 01  2e ff ff ff ff ff ff ff ff ff - transceiver data

00:    messageID
01:    length
02-03: address

Additional bytes frequency correction
05lo-07hi: frequency correction

Additional bytes transceiver data
05-10:     serial number
09-10:     DeviceID [devID]

-------------------------------------------------------------------------------
10. ReadConfigFlash out - ask for data

000: dd 0a 01 f5 cc cc cc cc cc cc  cc cc cc cc cc - Ask for freq correction
000: dd 0a 01 f9 cc cc cc cc cc cc  cc cc cc cc cc - Ask for transceiver data

00:    messageID
01:    length
02-03: address
04-14: cc

-------------------------------------------------------------------------------
11. GetState message

000:  de 14 00 00 00 00 (between SetPreamblePattern and first de16 message)
000:  de 15 00 00 00 00 Idle message
000:  de 16 00 00 00 00 Normal message
000:  de 0b 00 00 00 00 (detected via USB sniffer)

00:    messageID
01:    stateID
02-05: 00

-------------------------------------------------------------------------------
12. Writereg message

000: f0 08 01 00 00 - AX5051RegisterNames.IFMODE
000: f0 10 01 41 00 - AX5051RegisterNames.MODULATION
000: f0 11 01 07 00 - AX5051RegisterNames.ENCODING
...
000: f0 7b 01 88 00 - AX5051RegisterNames.TXRATEMID 
000: f0 7c 01 23 00 - AX5051RegisterNames.TXRATELO
000: f0 7d 01 35 00 - AX5051RegisterNames.TXDRIVER

00:    messageID
01:    register address
02:    01
03:    AX5051RegisterName
04:    00

-------------------------------------------------------------------------------
13. Current Weather message

start  hi-lo  chars  rem  name
0      hi     4           DevID
2      hi     2           Action
3      hi     2           Quality
4      hi     4           DeviceCS
6      hi     4      6    AlarmRingingFlags
8      hi     1           WeatherTendency
8      lo     1           WeatherState
9      hi     1           not used
9      lo     10          TempIndoorMaxDT
14     lo     10          TempIndoorMinDT
19     lo     5           TempIndoorMax
22     hi     5           TempIndoorMin
24     lo     5           TempIndoor                           (C)
27     lo     10          TempOutdoorMaxDT
32     lo     10          TempOutdoorMinDT
37     lo     5           TempOutdoorMax
40     hi     5           TempOutdoorMin
42     lo     5           TempOutdoor                          (C)
45     hi     1           not used
45     lo     10     1    WindchillMaxDT
50     lo     10     2    WindchillMinDT
55     lo     5      1    WindchillMax
57     hi     5      1    WindchillMin
60     lo     6           Windchill                            (C)
63     hi     1           not used
63     lo     10          DewpointMaxDT
68     lo     10          DewpointMinDT
73     lo     5           DewpointMax
76     hi     5           DewpointMin
78     lo     5           Dewpoint                             (C)
81     hi     10          HumidityIndoorMaxDT
86     hi     10          HumidityIndoorMinDT
91     hi     2           HumidityIndoorMax
92     hi     2           HumidityIndoorMin
93     hi     2           HumidityIndoor                       (%)
94     hi     10          HumidityOutdoorMaxDT
99     hi     10          HumidityOutdoorMinDT
104    hi     2           HumidityOutdoorMax
105    hi     2           HumidityOutdoorMin
106    hi     2           HumidityOutdoor                      (%)
107    hi     10     3    RainLastMonthMaxDT
112    hi     6      3    RainLastMonthMax
115    hi     6           RainLastMonth                        (mm)
118    hi     10     3    RainLastWeekMaxDT
123    hi     6      3    RainLastWeekMax
126    hi     6           RainLastWeek                         (mm)
129    hi     10          Rain24HMaxDT
134    hi     6           Rain24HMax
137    hi     6           Rain24H                              (mm)
140    hi     10          Rain24HMaxDT
145    hi     6           Rain24HMax
148    hi     6           Rain24H                              (mm)
151    hi     1           not used
152    lo     10          LastRainReset
158    lo     7           RainTotal                            (mm)
160    hi     1           WindDirection5
160    lo     1           WindDirection4
161    hi     1           WindDirection3
161    lo     1           WindDirection2
162    hi     1           WindDirection1
162    lo     1           WindDirection                        (0-15)
163    hi     18          unknown data
172    hi     6           WindSpeed                            (km/h)
175    hi     1           GustDirection5
175    lo     1           GustDirection4
176    hi     1           GustDirection3
176    lo     1           GustDirection2
177    hi     1           GustDirection1
177    lo     1           GustDirection                        (0-15)
178    hi     2           not used
179    hi     10          GustMaxDT
184    hi     6           GustMax
187    hi     6           Gust                                 (km/h)
190    hi     10     4    PressureRelative_Max.MinDT
195    hi     5      5    PressureRelative_inHgMax
197    lo     5      5    PressureRelative_hPaMax
200    hi     5           PressureRelative_inHgMax
202    lo     5           PressureRelative_hPaMax
205    hi     5           PressureRelative_inHgMin
207    lo     5           PressureRelative_hPaMin
210    hi     5           PressureRelative_inHg
212    lo     5           PressureRelative_hPa

214    lo     430         end

Remarks
  1 since factory reset
  2 since software reset
  3 not used?
  4 should be: PressureRelative_MaxDT
  5 should be: PressureRelativeMinDT
  6 AlarmRingingFlags (values in hex)
    80 00 = Hi Al Gust
    40 00 = Al WindDir
    20 00 = One or more WindDirs set
    10 00 = Hi Al Rain24H
    08 00 = Hi Al Outdoor Humidity
    04 00 = Lo Al Outdoor Humidity
    02 00 = Hi Al Indoor Humidity
    01 00 = Lo Al Indoor Humidity
    00 80 = Hi Al Outdoor Temp
    00 40 = Lo Al Outdoor Temp
    00 20 = Hi Al Indoor Temp
    00 10 = Lo Al Indoor Temp
    00 08 = Hi Al Pressure
    00 04 = Lo Al Pressure
    00 02 = not used
    00 01 = not used

-------------------------------------------------------------------------------
14. History Message

start  hi-lo  chars  rem  name
0      hi     4           DevID
2      hi     2           Action
3      hi     2           Quality          (%)
4      hi     4           DeviceCS
6      hi     6           LatestAddress
9      hi     6           ThisAddress
12     hi     1           not used
12     lo     3           Gust             (m/s)
14     hi     1           WindDirection    (0-15, also GustDirection)
14     lo     3           WindSpeed        (m/s)
16     hi     3           RainCounterRaw   (total in period in 0.1 inch)
17     lo     2           HumidityOutdoor  (%)
18     lo     2           HumidityIndoor   (%)
19     lo     5           PressureRelative (hPa)
22     hi     3           TempOutdoor      (C)
23     lo     3           TempIndoor       (C)
25     hi     10          Time

29     lo     60   end

-------------------------------------------------------------------------------
15. Set Config Message

start  hi-lo  chars  rem  name
0      hi     4           DevID
2      hi     2           Action
3      hi     2           Quality
4      hi     1       1   WindspeedFormat
4      lo     0,25    2   rain_format
4      lo     0,25    3   pressure_format
4      lo     0,25    4   TemperatureFormat
4      lo     0,25    5   ClockMode
5      hi     1           WeatherThreshold
5      lo     1           StormThreshold
6      hi     1           LowBatFlags
6      lo     1       6   LCDContrast
7      hi     4       7   WindDirAlarmFlags (reverse group 1)
9      hi     4       8   OtherAlarmFlags   (reverse group 1)
11     hi     10          TempIndoorMin (reverse group 2)
                          TempIndoorMax (reverse group 2)
16     hi     10          TempOutdoorMin (reverse group 3)
                          TempOutdoorMax (reverse group 3)
21     hi     2           HumidityIndoorMin
22     hi     2           HumidityIndoorMax
23     hi     2           HumidityOutdoorMin
24     hi     2           HumidityOutdoorMax
25     hi     1           not used
25     lo     7           Rain24HMax (reverse bytes)
29     hi     2           HistoryInterval
30     hi     1           not used
30     lo     5           GustMax (reverse bytes)
33     hi     10          PressureRelative_hPaMin (rev grp4)
                          PressureRelative_inHgMin(rev grp4)
38     hi     10          PressureRelative_hPaMax (rev grp5)
                          PressureRelative_inHgMax(rev grp5)
43     hi     6       9   ResetMinMaxFlags
46     hi     4       10  InBufCS

47     lo     96          end

Remarks 
  1 0=m/s 1=knots 2=bft 3=km/h 4=mph
  2 0=mm   1=inch
  3 0=inHg 2=hPa
  4 0=F    1=C
  5 0=24h  1=12h
  6 values 0-7 => LCD contrast 1-8
  7 WindDir Alarms (not-reversed values in hex)
    80 00 = NNW
    40 00 = NW
    20 00 = WNW
    10 00 = W
    08 00 = WSW
    04 00 = SW
    02 00 = SSW
    01 00 = S
    00 80 = SSE
    00 40 = SE
    00 20 = ESE
    00 10 = E
    00 08 = ENE
    00 04 = NE
    00 02 = NNE
    00 01 = N
  8 Other Alarms (not-reversed values in hex)
    80 00 = Hi Al Gust
    40 00 = Al WindDir
    20 00 = One or more WindDirs set
    10 00 = Hi Al Rain24H
    08 00 = Hi Al Outdoor Humidity
    04 00 = Lo Al Outdoor Humidity
    02 00 = Hi Al Indoor Humidity
    01 00 = Lo Al Indoor Humidity
    00 80 = Hi Al Outdoor Temp
    00 40 = Lo Al Outdoor Temp
    00 20 = Hi Al Indoor Temp
    00 10 = Lo Al Indoor Temp
    00 08 = Hi Al Pressure
    00 04 = Lo Al Pressure
    00 02 = not used
    00 01 = not used
  9 ResetMinMaxFlags (not-reversed values in hex)
    "Output only; not included in checksum calc"
    80 00 00 =  Reset DewpointMax
    40 00 00 =  Reset DewpointMin
    20 00 00 =  not used
    10 00 00 =  Reset WindchillMin*
    "*Reset dateTime only; Min is preserved"
    08 00 00 =  Reset TempOutMax
    04 00 00 =  Reset TempOutMin
    02 00 00 =  Reset TempInMax
    01 00 00 =  Reset TempInMin
    00 80 00 =  Reset Gust
    00 40 00 =  not used
    00 20 00 =  not used
    00 10 00 =  not used
    00 08 00 =  Reset HumOutMax
    00 04 00 =  Reset HumOutMin
    00 02 00 =  Reset HumInMax
    00 01 00 =  Reset HumInMin
    00 00 80 =  not used
    00 00 40 =  Reset Rain Total
    00 00 20 =  Reset last month?
    00 00 10 =  Reset lastweek?
    00 00 08 =  Reset Rain24H
    00 00 04 =  Reset Rain1H
    00 00 02 =  Reset PresRelMax
    00 00 01 =  Reset PresRelMin
  10 Checksum = sum bytes (0-42) + 7 

-------------------------------------------------------------------------------
16. Get Config Message

start  hi-lo  chars  rem  name
0      hi     4           DevID
2      hi     2           Action
3      hi     2           Quality
4      hi     1      1    WindspeedFormat
4      lo     0,25   2    rain_format
4      lo     0,25   3    pressure_format
4      lo     0,25   4    TemperatureFormat
4      lo     0,25   5    ClockMode
5      hi     1           WeatherThreshold
5      lo     1           StormThreshold
6      hi     1           LowBatFlags
6      lo     1      6    LCDContrast
7      hi     4      7    WindDirAlarmFlags
9      hi     4      8    OtherAlarmFlags
11     hi     5           TempIndoorMin
13     lo     5           TempIndoorMax
16     hi     5           TempOutdoorMin
18     lo     5           TempOutdoorMax
21     hi     2           HumidityIndoorMax
22     hi     2           HumidityIndoorMin
23     hi     2           HumidityOutdoorMax
24     hi     2           HumidityOutdoorMin
25     hi     1           not used
25     lo     7           Rain24HMax
29     hi     2           HistoryInterval
30     hi     5           GustMax
32     lo     1           not used
33     hi     5           PressureRelative_hPaMin
35     lo     5           PressureRelative_inHgMin
38     hi     5           PressureRelative_hPaMax
40     lo     5           PressureRelative_inHgMax
43     hi     6      9    ResetMinMaxFlags
46     hi     4      10   InBufCS

47     lo     96          end

Remarks
  1 0=m/s 1=knots 2=bft 3=km/h 4=mph
  2 0=mm   1=inch
  3 0=inHg 2=hPa
  4 0=F    1=C
  5 0=24h  1=12h
  6 values 0-7 => LCD contrast 1-8
  7 WindDir Alarms (values in hex)
    80 00 = NNW
    40 00 = NW
    20 00 = WNW
    10 00 = W
    08 00 = WSW
    04 00 = SW
    02 00 = SSW
    01 00 = S
    00 80 = SSE
    00 40 = SE
    00 20 = ESE
    00 10 = E
    00 08 = ENE
    00 04 = NE
    00 02 = NNE
    00 01 = N
  8 Other Alarms (values in hex)
    80 00 = Hi Al Gust
    40 00 = Al WindDir
    20 00 = One or more WindDirs set
    10 00 = Hi Al Rain24H
    08 00 = Hi Al Outdoor Humidity
    04 00 = Lo Al Outdoor Humidity
    02 00 = Hi Al Indoor Humidity
    01 00 = Lo Al Indoor Humidity
    00 80 = Hi Al Outdoor Temp
    00 40 = Lo Al Outdoor Temp
    00 20 = Hi Al Indoor Temp
    00 10 = Lo Al Indoor Temp
    00 08 = Hi Al Pressure
    00 04 = Lo Al Pressure
    00 02 = not used
    00 01 = not used
  9 ResetMinMaxFlags (values in hex)
    "Output only; input =  00 00 00"
  10 Checksum = sum bytes (0-42) + 7 


-------------------------------------------------------------------------------
Examples of messages

readCurrentWeather
Cur   000: 01 2e 60 5f 05 1b 00 00 12 01  30 62 21 54 41 30 62 40 75 36  
Cur   020: 59 00 60 70 06 35 00 01 30 62  31 61 21 30 62 30 55 95 92 00  
Cur   040: 53 10 05 37 00 01 30 62 01 90  81 30 62 40 90 66 38 00 49 00  
Cur   060: 05 37 00 01 30 62 21 53 01 30  62 22 31 75 51 11 50 40 05 13  
Cur   080: 80 13 06 22 21 40 13 06 23 19  37 67 52 59 13 06 23 06 09 13  
Cur   100: 06 23 16 19 91 65 86 00 00 00  00 00 00 00 00 00 00 00 00 00  
Cur   120: 00 00 00 00 00 00 00 00 00 13  06 23 09 59 00 06 19 00 00 51  
Cur   140: 13 06 22 20 43 00 01 54 00 00  00 01 30 62 21 51 00 00 38 70  
Cur   160: a7 cc 7b 50 09 01 01 00 00 00  00 00 00 fc 00 a7 cc 7b 14 13  
Cur   180: 06 23 14 06 0e a0 00 01 b0 00  13 06 23 06 34 03 00 91 01 92  
Cur   200: 03 00 91 01 92 02 97 41 00 74  03 00 91 01 92
 
WeatherState: Sunny(Good)  WeatherTendency: Rising(Up)  AlarmRingingFlags: 0000
TempIndoor      23.500 Min:20.700 2013-06-24 07:53 Max:25.900 2013-06-22 15:44
HumidityIndoor  59.000 Min:52.000 2013-06-23 19:37 Max:67.000 2013-06-22 21:40
TempOutdoor     13.700 Min:13.100 2013-06-23 05:59 Max:19.200 2013-06-23 16:12
HumidityOutdoor 86.000 Min:65.000 2013-06-23 16:19 Max:91.000 2013-06-23 06:09
Windchill       13.700 Min: 9.000 2013-06-24 09:06 Max:23.800 2013-06-20 19:08
Dewpoint        11.380 Min:10.400 2013-06-22 23:17 Max:15.111 2013-06-22 15:30
WindSpeed        2.520
Gust             4.320                             Max:37.440 2013-06-23 14:06
WindDirection    WSW    GustDirection    WSW
WindDirection1   SSE    GustDirection1   SSE
WindDirection2     W    GustDirection2     W
WindDirection3     W    GustDirection3     W
WindDirection4   SSE    GustDirection4   SSE
WindDirection5    SW    GustDirection5    SW
RainLastMonth    0.000                             Max: 0.000 1900-01-01 00:00
RainLastWeek     0.000                             Max: 0.000 1900-01-01 00:00
Rain24H          0.510                             Max: 6.190 2013-06-23 09:59
Rain1H           0.000                             Max: 1.540 2013-06-22 20:43
RainTotal        3.870                    LastRainReset       2013-06-22 15:10
PresRelhPa 1019.200 Min:1007.400 2013-06-23 06:34 Max:1019.200 2013-06-23 06:34
PresRel_inHg 30.090 Min:  29.740 2013-06-23 06:34 Max:  30.090 2013-06-23 06:34
Bytes with unknown meaning at 157-165: 50 09 01 01 00 00 00 00 00 

-------------------------------------------------------------------------------
readHistory
His   000: 01 2e 80 5f 05 1b 00 7b 32 00  7b 32 00 0c 70 0a 00 08 65 91  
His   020: 01 92 53 76 35 13 06 24 09 10 
 
Time           2013-06-24 09:10:00
TempIndoor=          23.5
HumidityIndoor=        59
TempOutdoor=         13.7
HumidityOutdoor=       86
PressureRelative=  1019.2
RainCounterRaw=       0.0
WindDirection=        SSE
WindSpeed=            1.0
Gust=                 1.2

-------------------------------------------------------------------------------
readConfig
In   000: 01 2e 40 5f 36 53 02 00 00 00  00 81 00 04 10 00 82 00 04 20  
In   020: 00 71 41 72 42 00 05 00 00 00  27 10 00 02 83 60 96 01 03 07  
In   040: 21 04 01 00 00 00 05 1b

-------------------------------------------------------------------------------
writeConfig
Out  000: 01 2e 40 64 36 53 02 00 00 00  00 00 10 04 00 81 00 20 04 00  
Out  020: 82 41 71 42 72 00 00 05 00 00  00 10 27 01 96 60 83 02 01 04  
Out  040: 21 07 03 10 00 00 05 1b 

OutBufCS=             051b
ClockMode=            0
TemperatureFormat=    1
pressure_format=       1
rain_format=           0
WindspeedFormat=      3
WeatherThreshold=     3
StormThreshold=       5
LCDContrast=          2
LowBatFlags=          0
WindDirAlarmFlags=    0000
OtherAlarmFlags=      0000
HistoryInterval=      0
TempIndoorMin=       1.0
TempIndooMax=       41.0
TempOutdoorMin=      2.0
TempOutdooMax=      42.0
HumidityIndoorMin=   41
HumidityIndooMax=   71
HumidityOutdoorMin=  42
HumidityOutdooMax=  72
Rain24HMax=           50.0
GustMax=              100.0
PressureRel_hPaMin=  960.1
PressureRel_inHgMin= 28.36
PressureRel_hPMax=  1040.1
PressureRel_inHMax= 30.72
ResetMinMaxFlags=     100000 (Output only; Input always 00 00 00)

-------------------------------------------------------------------------------
Constant  Value Message received at
hi01Min   = 0   00:00, 00:01, 00:02, 00:03 ... 23:59
hi05Min   = 1   00:00, 00:05, 00:10, 00:15 ... 23:55
hi10Min   = 2   00:00, 00:10, 00:20, 00:30 ... 23:50
hi15Min   = 3   00:00, 00:15, 00:30, 00:45 ... 23:45
hi20Min   = 4   00:00, 00:20, 00:40, 01:00 ... 23:40
hi30Min   = 5   00:00, 00:30, 01:00, 01:30 ... 23:30
hi01Std   = 6   00:00, 01:00, 02:00, 03:00 ... 23:00
hi02Std   = 7   00:00, 02:00, 04:00, 06:00 ... 22:00
hi04Std   = 8   00:00, 04:00, 08:00, 12:00 ... 20:00
hi06Std   = 9   00:00, 06:00, 12:00, 18:00
hi08Std   = 0xA 00:00, 08:00, 16:00
hi12Std   = 0xB 00:00, 12:00
hi24Std   = 0xC 00:00

-------------------------------------------------------------------------------
WS SetTime - Send time to WS
Time  000: 01 2e c0 05 1b 19 14 12 40 62  30 01
time sent: 2013-06-24 12:14:19 

-------------------------------------------------------------------------------
ReadConfigFlash data

Ask for frequency correction 
rcfo  000: dd 0a 01 f5 cc cc cc cc cc cc  cc cc cc cc cc

readConfigFlash frequency correction
rcfi  000: dc 0a 01 f5 00 01 78 a0 01 02  0a 0c 0c 01 2e ff ff ff ff ff
frequency correction: 96416 (0x178a0)
adjusted frequency: 910574957 (3646456d)

Ask for transceiver data 
rcfo  000: dd 0a 01 f9 cc cc cc cc cc cc  cc cc cc cc cc

readConfigFlash serial number and DevID
rcfi  000: dc 0a 01 f9 01 02 0a 0c 0c 01  2e ff ff ff ff ff ff ff ff ff
transceiver ID: 302 (0x012e)
transceiver serial: 01021012120146

Program Logic

The RF communication thread uses the following logic to communicate with the
weather station console:

Step 1.  Perform in a while loop getState commands until state 0xde16
         is received.

Step 2.  Perform a getFrame command to read the message data.

Step 3.  Handle the contents of the message. The type of message depends on
         the response type:

  Response type (hex):
  20: WS SetTime / SetConfig - Data written
      confirmation the setTime/setConfig setFrame message has been received
      by the console
  40: GetConfig
      save the contents of the configuration for later use (i.e. a setConfig
      message with one ore more parameters changed)
  60: Current Weather
      handle the weather data of the current weather message
  80: Actual / Outstanding History
      ignore the data of the actual history record when there is no data gap;
      handle the data of a (one) requested history record (note: in step 4 we
      can decide to request another history record).
  a1: Request First-Time Config
      prepare a setFrame first time message
  a2: Request SetConfig
      prepare a setFrame setConfig message
  a3: Request SetTime
      prepare a setFrame setTime message

Step 4.  When  you  didn't receive the message in step 3 you asked for (see
         step 5 how to request a certain type of message), decide if you want
         to ignore or handle the received message. Then go to step 5 to
         request for a certain type of message unless the received message
         has response type a1, a2 or a3, then prepare first the setFrame
         message the wireless console asked for.

Step 5.  Decide what kind of message you want to receive next time. The
         request is done via a setFrame message (see step 6).  It is
         not guaranteed that you will receive that kind of message the next
         time but setting the proper timing parameters of firstSleep and
         nextSleep increase the chance you will get the requested type of
         message.

Step 6. The action parameter in the setFrame message sets the type of the
        next to receive message.

  Action (hex):
  00: rtGetHistory - Ask for History message
                     setSleep(0.300,0.010)
  01: rtSetTime    - Ask for Send Time to weather station message
                     setSleep(0.085,0.005)
  02: rtSetConfig  - Ask for Send Config to weather station message
                     setSleep(0.300,0.010)
  03: rtGetConfig  - Ask for Config message
                     setSleep(0.400,0.400)
  05: rtGetCurrent - Ask for Current Weather message
                     setSleep(0.300,0.010)
  c0: Send Time    - Send Time to WS
                     setSleep(0.085,0.005)
  40: Send Config  - Send Config to WS
                     setSleep(0.085,0.005)

  Note: after the Request First-Time Config message (response type = 0xa1)
        perform a rtGetConfig with setSleep(0.085,0.005)

Step 7. Perform a setTX command

Step 8. Go to step 1 to wait for state 0xde16 again.

"""

# TODO: how often is currdat.lst modified with/without hi-speed mode?
# TODO: thread locking around observation data
# TODO: eliminate polling, make MainThread get data as soon as RFThread updates
# TODO: get rid of length/buffer construct, replace with a buffer class or obj

# FIXME: the history retrieval assumes a constant archive interval across all
#        history records.  this means anything that modifies the archive
#        interval should clear the history.

from datetime import datetime

import StringIO
import sys
import syslog
import threading
import time
import traceback
import usb

import weewx.drivers
import weewx.wxformulas
import weeutil.weeutil

DRIVER_NAME = 'WS28xx'
DRIVER_VERSION = '0.34-lh'


def loader(config_dict, _):
    return WS28xxDriver(**config_dict[DRIVER_NAME])


def configurator_loader(_):
    return WS28xxConfigurator()


def confeditor_loader():
    return WS28xxConfEditor()


# flags for enabling/disabling debug verbosity
DEBUG_COMM = 0
DEBUG_CONFIG_DATA = 0
DEBUG_WEATHER_DATA = 0
DEBUG_HISTORY_DATA = 0
DEBUG_DUMP_FORMAT = 'auto'


def logmsg(dst, msg):
    syslog.syslog(dst, 'ws28xx: %s: %s' %
                  (threading.currentThread().getName(), msg))


def logdbg(msg):
    logmsg(syslog.LOG_DEBUG, msg)


def loginf(msg):
    logmsg(syslog.LOG_INFO, msg)


def logcrt(msg):
    logmsg(syslog.LOG_CRIT, msg)


def logerr(msg):
    logmsg(syslog.LOG_ERR, msg)


def log_traceback(dst=syslog.LOG_INFO, prefix='**** '):
    sfd = StringIO.StringIO()
    traceback.print_exc(file=sfd)
    sfd.seek(0)
    for line in sfd:
        logmsg(dst, prefix + line)
    del sfd


def log_frame(n, buf):
    logdbg('frame length is %d' % n)
    strbuf = ''
    for i in xrange(0, n):
        strbuf += str('%02x ' % buf[i])
        if (i + 1) % 16 == 0:
            logdbg(strbuf)
            strbuf = ''
    if strbuf:
        logdbg(strbuf)


def get_datum_diff(v, np, ofl):
    if abs(np - v) < 0.001 or abs(ofl - v) < 0.001:
        return None
    return v


def get_datum_match(v, np, ofl):
    if np == v or ofl == v:
        return None
    return v


def calc_checksum(buf, start, end=None):
    if end is None:
        end = len(buf[0])
    cs = 0
    for i in xrange(start, end):
        cs += buf[0][i]
    return cs


def get_next_index(idx):
    return get_index(idx + 1)


def get_index(idx):
    if idx < 0:
        return idx + WS28xxDriver.max_records
    elif idx >= WS28xxDriver.max_records:
        return idx - WS28xxDriver.max_records
    return idx


def tstr_to_ts(tstr):
    try:
        return int(time.mktime(time.strptime(tstr, "%Y-%m-%d %H:%M:%S")))
    except (OverflowError, ValueError, TypeError):
        pass
    return None


def bytes_to_addr(a, b, c):
    return ((((a & 0xF) << 8) | b) << 8) | c


def addr_to_index(addr):
    return (addr - 416) / 18


def index_to_addr(idx):
    return 18 * idx + 416


def print_dict(data):
    for x in sorted(data.keys()):
        if x == 'dateTime':
            print '%s: %s' % (x, weeutil.weeutil.timestamp_to_string(data[x]))
        else:
            print '%s: %s' % (x, data[x])


class WS28xxConfEditor(weewx.drivers.AbstractConfEditor):
    @property
    def default_stanza(self):
        return """
[WS28xx]
    # This section is for the La Crosse WS-2800 series of weather stations.

    # Radio frequency to use between USB transceiver and console: US or EU
    # US uses 915 MHz, EU uses 868.3 MHz.  Default is US.
    transceiver_frequency = US

    # The station model, e.g., 'LaCrosse C86234' or 'TFA Primus'
    model = LaCrosse WS28xx

    # The driver to use:
    driver = weewx.drivers.ws28xx
"""

    def prompt_for_settings(self):
        print "Specify the frequency used between the station and the"
        print "transceiver, either 'US' (915 MHz) or 'EU' (868.3 MHz)."
        freq = self.prompt('frequency', 'US', ['US', 'EU'])
        return {'transceiver_frequency': freq}


class WS28xxConfigurator(weewx.drivers.AbstractConfigurator):
    def add_options(self, parser):
        super(WS28xxConfigurator, self).add_options(parser)
        parser.add_option("--check-transceiver", dest="check",
                          action="store_true",
                          help="check USB transceiver")
        parser.add_option("--pair", dest="pair", action="store_true",
                          help="pair the USB transceiver with station console")
        parser.add_option("--info", dest="info", action="store_true",
                          help="display weather station configuration")
        parser.add_option("--set-interval", dest="interval",
                          type=int, metavar="N",
                          help="set logging interval to N minutes")
        parser.add_option("--current", dest="current", action="store_true",
                          help="get the current weather conditions")
        parser.add_option("--history", dest="nrecords", type=int, metavar="N",
                          help="display N history records")
        parser.add_option("--history-since", dest="recmin",
                          type=int, metavar="N",
                          help="display history records since N minutes ago")
        parser.add_option("--maxtries", dest="maxtries", type=int,
                          help="maximum number of retries, 0 indicates no max")

    def do_options(self, options, parser, config_dict, prompt):
        maxtries = 3 if options.maxtries is None else int(options.maxtries)
        self.station = WS28xxDriver(**config_dict[DRIVER_NAME])
        if options.check:
            self.check_transceiver(maxtries)
        elif options.pair:
            self.pair(maxtries)
        elif options.interval is not None:
            self.set_interval(maxtries, options.interval, prompt)
        elif options.current:
            self.show_current(maxtries)
        elif options.nrecords is not None:
            self.show_history(maxtries, count=options.nrecords)
        elif options.recmin is not None:
            ts = int(time.time()) - options.recmin * 60
            self.show_history(maxtries, ts=ts)
        else:
            self.show_info(maxtries)
        self.station.closePort()

    def check_transceiver(self, maxtries):
        """See if the transceiver is installed and operational."""
        print 'Checking for transceiver...'
        ntries = 0
        while ntries < maxtries:
            ntries += 1
            if self.station.transceiver_is_present():
                print 'Transceiver is present'
                sn = self.station.get_transceiver_serial()
                print 'serial: %s' % sn
                tid = self.station.get_transceiver_id()
                print 'id: %d (0x%04x)' % (tid, tid)
                break
            print 'Not found (attempt %d of %d) ...' % (ntries, maxtries)
            time.sleep(5)
        else:
            print 'Transceiver not responding.'

    def pair(self, maxtries):
        """Pair the transceiver with the station console."""
        print 'Pairing transceiver with console...'
        maxwait = 90  # how long to wait between button presses, in seconds
        ntries = 0
        while ntries < maxtries or maxtries == 0:
            if self.station.transceiver_is_paired():
                print 'Transceiver is paired to console'
                break
            ntries += 1
            msg = 'Press and hold the [v] key until "PC" appears'
            if maxtries > 0:
                msg += ' (attempt %d of %d)' % (ntries, maxtries)
            else:
                msg += ' (attempt %d)' % ntries
            print msg
            now = start_ts = int(time.time())
            while (now - start_ts < maxwait and
                   not self.station.transceiver_is_paired()):
                time.sleep(5)
                now = int(time.time())
        else:
            print 'Transceiver not paired to console.'

    def get_interval(self, maxtries):
        cfg = self.get_config(maxtries)
        if cfg is None:
            return None
        return history_intervals.get(cfg['history_interval'])

    def get_config(self, maxtries):
        start_ts = None
        ntries = 0
        while ntries < maxtries or maxtries == 0:
            cfg = self.station.get_config()
            if cfg is not None:
                return cfg
            ntries += 1
            if start_ts is None:
                start_ts = int(time.time())
            else:
                dur = int(time.time()) - start_ts
                print 'No data after %d seconds (press SET to sync)' % dur
            time.sleep(30)
        return None

    @staticmethod
    def set_interval(maxtries, interval, prompt):
        """Set the station archive interval"""
        print "This feature is not yet implemented"

    def show_info(self, maxtries):
        """Query the station then display the settings."""
        print 'Querying the station for the configuration...'
        cfg = self.get_config(maxtries)
        if cfg is not None:
            print_dict(cfg)

    def show_current(self, maxtries):
        """Get current weather observation."""
        print 'Querying the station for current weather data...'
        start_ts = None
        ntries = 0
        while ntries < maxtries or maxtries == 0:
            packet = self.station.get_observation()
            if packet is not None:
                print_dict(packet)
                break
            ntries += 1
            if start_ts is None:
                start_ts = int(time.time())
            else:
                dur = int(time.time()) - start_ts
                print 'No data after %d seconds (press SET to sync)' % dur
            time.sleep(30)

    def show_history(self, maxtries, ts=0, count=0):
        """Display the indicated number of records or the records since the 
        specified timestamp (local time, in seconds)"""
        print "Querying the station for historical records..."
        ntries = 0
        last_n = nrem = None
        last_ts = int(time.time())
        self.station.start_caching_history(since_ts=ts, num_rec=count)
        while nrem is None or nrem > 0:
            if ntries >= maxtries:
                print 'Giving up after %d tries' % ntries
                break
            time.sleep(30)
            ntries += 1
            now = int(time.time())
            n = self.station.get_num_history_scanned()
            if n == last_n:
                dur = now - last_ts
                print 'No data after %d seconds (press SET to sync)' % dur
            else:
                ntries = 0
                last_ts = now
            last_n = n
            nrem = self.station.get_uncached_history_count()
            ni = self.station.get_next_history_index()
            li = self.station.get_latest_history_index()
            msg = "  scanned %s records: current=%s latest=%s remaining=%s\r" % (n, ni, li, nrem)
            sys.stdout.write(msg)
            sys.stdout.flush()
        self.station.stop_caching_history()
        records = self.station.get_history_cache_records()
        self.station.clear_history_cache()
        print
        print 'Found %d records' % len(records)
        for r in records:
            print r


class WS28xxDriver(weewx.drivers.AbstractDevice):
    """Driver for LaCrosse WS28xx stations."""

    max_records = 1797

    def __init__(self, **stn_dict):
        """Initialize the station object.

        model: Which station model is this?
        [Optional. Default is 'LaCrosse WS28xx']

        transceiver_frequency: Frequency for transceiver-to-console.  Specify
        either US or EU.
        [Required. Default is US]

        polling_interval: How often to sample the USB interface for data.
        [Optional. Default is 30 seconds]

        comm_interval: Communications mode interval
        [Optional.  Default is 3]

        device_id: The USB device ID for the transceiver.  If there are
        multiple devices with the same vendor and product IDs on the bus,
        each will have a unique device identifier.  Use this identifier
        to indicate which device should be used.
        [Optional. Default is None]

        serial: The transceiver serial number.  If there are multiple
        devices with the same vendor and product IDs on the bus, each will
        have a unique serial number.  Use the serial number to indicate which
        transceiver should be used.
        [Optional. Default is None]
        """

        self.vendor_id = stn_dict.get('vendor_id', 0x6666)
        self.product_id = stn_dict.get('product_id', 0x5555)
        self.model = stn_dict.get('model', 'LaCrosse WS28xx')
        self.polling_interval = int(stn_dict.get('polling_interval', 10))
        self.comm_interval = int(stn_dict.get('comm_interval', 6))
        self.frequency = stn_dict.get('transceiver_frequency', 'EU')
        self.serial = stn_dict.get('serial', None)

        now = int(time.time())
        self.service = None
        self.last_obs_ts = None
        self.last_nodata_log_ts = now
        self.nodata_interval = 300  # how often to check for no data
        self.last_contact_log_ts = now
        self.nocontact_interval = 300  # how often to check for no contact
        self.log_interval = 600  # how often to log
        self.packet_count = 0
        self.empty_packet_count = 0
        self.last_rain = 0

        global DEBUG_COMM
        DEBUG_COMM = int(stn_dict.get('debug_comm', 0))
        global DEBUG_CONFIG_DATA
        DEBUG_CONFIG_DATA = int(stn_dict.get('debug_config_data', 0))
        global DEBUG_WEATHER_DATA
        DEBUG_WEATHER_DATA = int(stn_dict.get('debug_weather_data', 0))
        global DEBUG_HISTORY_DATA
        DEBUG_HISTORY_DATA = int(stn_dict.get('debug_history_data', 0))
        global DEBUG_DUMP_FORMAT
        DEBUG_DUMP_FORMAT = stn_dict.get('debug_dump_format', 'auto')

        loginf('driver version is %s' % DRIVER_VERSION)
        loginf('frequency is %s' % self.frequency)

        self.startUp()

    @property
    def hardware_name(self):
        return self.model

    # this is invoked by StdEngine as it shuts down
    def closePort(self):
        self.shutDown()

    def genLoopPackets(self):
        """Generator function that continuously returns decoded packets."""
        while True:
            self.packet_count += 1
            now = int(time.time() + 0.5)
            packet = self.get_observation()
            if packet is not None:
                ts = packet['dateTime']
                if DEBUG_WEATHER_DATA > 0:
                    logdbg('packet_count=%s: ts=%s packet=%s' %
                           (self.packet_count, ts, packet))
                if self.last_obs_ts is None or self.last_obs_ts != ts:
                    self.last_obs_ts = ts
                    self.empty_packet_count = 0
                    self.last_nodata_log_ts = now
                    self.last_contact_log_ts = now
                else:
                    if DEBUG_WEATHER_DATA > 0:
                        logdbg("timestamp unchanged, set to empty packet")
                    packet = None
                    self.empty_packet_count += 1
            else:
                self.empty_packet_count += 1

            # if no new weather data, return an empty packet
            if packet is None:
                if DEBUG_WEATHER_DATA > 0:
                    logdbg("packet_count=%s empty_count=%s" %
                           (self.packet_count, self.empty_packet_count))
                if self.empty_packet_count >= 30:  # 30 * 10 s = 300 s
                    if DEBUG_WEATHER_DATA > 0:
                        msg = "Restarting communication after %d empty packets" % self.empty_packet_count
                        logdbg(msg)
                        raise weewx.WeeWxIOError('%s; press [USB] to sync' % msg)
                packet = {'usUnits': weewx.METRIC, 'dateTime': now}
                # if no new weather data for awhile, log it
                if self.last_obs_ts is None or now - self.last_obs_ts > self.nodata_interval:
                    if now - self.last_nodata_log_ts > self.log_interval:
                        msg = 'no new weather data'
                        if self.last_obs_ts is not None:
                            msg += ' after %d seconds' % (
                                now - self.last_obs_ts)
                        loginf(msg)
                        self.last_nodata_log_ts = now

            # if no contact with console for awhile, log it
            ts = self.get_last_contact()
            if ts is None or now - ts > self.nocontact_interval:
                if now - self.last_contact_log_ts > self.log_interval:
                    msg = 'no contact with console'
                    if ts is not None:
                        msg += ' after %d seconds' % (now - ts)
                    msg += ': press [USB] to sync'
                    loginf(msg)
                    self.last_contact_log_ts = now

            yield packet
            time.sleep(self.polling_interval)

    def genStartupRecords(self, ts):
        loginf('Scanning historical records')
        self.clear_wait_at_start()  # let rf communication start
        maxtries = 65
        ntries = 0
        last_n = nrem = None
        last_ts = int(time.time())
        self.start_caching_history(since_ts=ts)
        while nrem is None or nrem > 0:
            if ntries >= maxtries:
                logerr('No historical data after %d tries' % ntries)
                return
            time.sleep(60)
            ntries += 1
            now = int(time.time())
            n = self.get_num_history_scanned()
            if n == last_n:
                dur = now - last_ts
                loginf('No data after %d seconds (press [SET] to sync)' % dur)
            else:
                ntries = 0
                last_ts = now
            last_n = n
            nrem = self.get_uncached_history_count()
            ni = self.get_next_history_index()
            li = self.get_latest_history_index()
            loginf("Scanned %s records: current=%s latest=%s remaining=%s" %
                   (n, ni, li, nrem))
        self.stop_caching_history()
        records = self.get_history_cache_records()
        self.clear_history_cache()
        loginf('Found %d historical records' % len(records))
        last_ts = None
        for rec in records:
            this_ts = rec['dateTime']
            if last_ts is not None and this_ts is not None:
                rec['usUnits'] = weewx.METRIC
                rec['interval'] = (this_ts - last_ts) / 60
                yield rec
            last_ts = this_ts

    def startUp(self):
        if self.service is not None:
            return
        self.service = CommunicationService()
        self.service.setup(self.frequency, self.comm_interval, self.vendor_id, self.product_id, self.serial)
        self.service.startRFThread()

    def shutDown(self):
        self.service.stopRFThread()
        self.service.teardown()
        self.service = None

    def transceiver_is_present(self):
        return self.service.getTransceiverPresent()

    def transceiver_is_paired(self):
        return self.service.getDeviceRegistered()

    def get_transceiver_serial(self):
        return self.service.getTransceiverSerNo()

    def get_transceiver_id(self):
        return self.service.getDeviceID()

    def get_last_contact(self):
        return self.service.getLastStat().last_seen_ts

    def get_observation(self):
        data = self.service.getCurrentData()
        ts = data.timestamp
        if ts is None:
            return None

        # add elements required for weewx LOOP packets
        packet = {}
        packet['usUnits'] = weewx.METRIC
        packet['dateTime'] = ts

        # data from the station sensors
        packet['inTemp'] = get_datum_diff(data.TempIndoor,
                                          SensorLimits.temperature_NP,
                                          SensorLimits.temperature_OFL)
        packet['inHumidity'] = get_datum_diff(data.HumidityIndoor,
                                              SensorLimits.humidity_NP,
                                              SensorLimits.humidity_OFL)
        packet['outTemp'] = get_datum_diff(data.TempOutdoor,
                                           SensorLimits.temperature_NP,
                                           SensorLimits.temperature_OFL)
        packet['outHumidity'] = get_datum_diff(data.HumidityOutdoor,
                                               SensorLimits.humidity_NP,
                                               SensorLimits.humidity_OFL)
        packet['pressure'] = get_datum_diff(data.PressureRelative_hPa,
                                            SensorLimits.pressure_NP,
                                            SensorLimits.pressure_OFL)
        packet['windSpeed'] = get_datum_diff(data.WindSpeed,
                                             SensorLimits.wind_NP,
                                             SensorLimits.wind_OFL)
        packet['windGust'] = get_datum_diff(data.Gust,
                                            SensorLimits.wind_NP,
                                            SensorLimits.wind_OFL)

        packet['windDir'] = getWindDir(data.WindDirection,
                                       packet['windSpeed'])
        packet['windGustDir'] = getWindDir(data.GustDirection,
                                           packet['windGust'])

        # calculated elements not directly reported by station
        packet['rainRate'] = get_datum_match(data.Rain1H,
                                             SensorLimits.rain_NP,
                                             SensorLimits.rain_OFL)
        if packet['rainRate'] is not None:
            packet['rainRate'] /= 10  # weewx wants cm/hr
        rain_total = get_datum_match(data.RainTotal,
                                     SensorLimits.rain_NP,
                                     SensorLimits.rain_OFL)
        delta = weewx.wxformulas.calculate_rain(rain_total, self.last_rain)
        self.last_rain = rain_total
        packet['rain'] = delta
        if packet['rain'] is not None:
            packet['rain'] /= 10  # weewx wants cm

        # track the signal strength and battery levels
        last_stat = self.service.getLastStat()
        packet['rxCheckPercent'] = last_stat.last_link_quality
        packet['windBatteryStatus'] = getBatteryStatus(
            last_stat.last_battery_status, 'wind')
        packet['rainBatteryStatus'] = getBatteryStatus(
            last_stat.last_battery_status, 'rain')
        packet['outTempBatteryStatus'] = getBatteryStatus(
            last_stat.last_battery_status, 'th')
        packet['inTempBatteryStatus'] = getBatteryStatus(
            last_stat.last_battery_status, 'console')

        return packet

    def get_config(self):
        logdbg('get station configuration')
        cfg = self.service.getConfigData().asDict()
        cs = cfg.get('checksum_out')
        if cs is None or cs == 0:
            return None
        return cfg

    def start_caching_history(self, since_ts=0, num_rec=0):
        self.service.startCachingHistory(since_ts, num_rec)

    def stop_caching_history(self):
        self.service.stopCachingHistory()

    def get_uncached_history_count(self):
        return self.service.getUncachedHistoryCount()

    def get_next_history_index(self):
        return self.service.getNextHistoryIndex()

    def get_latest_history_index(self):
        return self.service.getLatestHistoryIndex()

    def get_num_history_scanned(self):
        return self.service.getNumHistoryScanned()

    def get_history_cache_records(self):
        return self.service.getHistoryCacheRecords()

    def clear_history_cache(self):
        self.service.clearHistoryCache()

    def clear_wait_at_start(self):
        self.service.clearWaitAtStart()

    def set_interval(self, interval):
        # FIXME: set the archive interval
        pass

# The following classes and methods are adapted from the implementation by
# eddie de pieri, which is in turn based on the HeavyWeather implementation.


class BadResponse(Exception):
    """raised when unexpected data found in frame buffer"""
    pass


class DataWritten(Exception):
    """raised when message 'data written' in frame buffer"""
    pass


class BitHandling:
    # return a nonzero result, 2**offset, if the bit at 'offset' is one.

    @staticmethod
    def testBit(int_type, offset):
        mask = 1 << offset
        return int_type & mask


WINDSPEED_FORMAT_MS = 0
WINDSPEED_FORMAT_KNOTS = 1
WINDSPEED_FORMAT_BFT = 2
WINDSPEED_FORMAT_KMH = 3
WINDSPEED_FORMAT_MPH = 4

RAIN_FORMAT_MM = 0
RAIN_FORMAT_INCH = 1

PRESSURE_FORMAT_INHG = 0
PRESSURE_FORMAT_HPA = 1

TEMPERATURE_FORMAT_FAHRENHEIT = 0
TEMPERATURE_FORMAT_CELSIUS = 1

TREND_NEUTRAL = 0
TREND_UP = 1
TREND_DOWN = 2
TREND_ERR = 3

WEATHER_BAD = 0
WEATHER_NEUTRAL = 1
WEATHER_GOOD = 2
WEATHER_ERR = 3

WIND_DIRECTION_N = 0
WIND_DIRECTION_NNE = 1
WIND_DIRECTION_NE = 2
WIND_DIRECTION_ENE = 3
WIND_DIRECTION_E = 4
WIND_DIRECTION_ESE = 5
WIND_DIRECTION_SE = 6
WIND_DIRECTION_SSE = 7
WIND_DIRECTION_S = 8
WIND_DIRECTION_SSW = 9
WIND_DIRECTION_SW = 0x0A
WIND_DIRECTION_WSW = 0x0B
WIND_DIRECTION_W = 0x0C
WIND_DIRECTION_WNW = 0x0D
WIND_DIRECTION_NW = 0x0E
WIND_DIRECTION_NNW = 0x0F
WIND_DIRECTION_ERR = 0x10
WIND_DIRECTION_INVALID = 0x11
WIND_DIRECTION_NONE = 0x12

RESET_MIN_MAX_FLAG_TEMP_INDOOR_HI = 0
RESET_MIN_MAX_FLAG_TEMP_INDOOR_LO = 1
RESET_MIN_MAX_FLAG_TEMP_OUTDOOR_HI = 2
RESET_MIN_MAX_FLAG_TEMP_OUTDOOR_LO = 3
RESET_MIN_MAX_FLAG_WINDCHILL_HI = 4
RESET_MIN_MAX_FLAG_WINDCHILL_LO = 5
RESET_MIN_MAX_FLAG_DEWPOINT_HI = 6
RESET_MIN_MAX_FLAG_DEWPOINT_LO = 7
RESET_MIN_MAX_FLAG_HUMIDITY_INDOOR_LO = 8
RESET_MIN_MAX_FLAG_HUMIDITY_INDOOR_HI = 9
RESET_MIN_MAX_FLAG_HUMIDITY_OUTDOOR_LO = 0x0A
RESET_MIN_MAX_FLAG_HUMIDITY_OUTDOOR_HI = 0x0B
RESET_MIN_MAX_FLAG_WINDSPEED_HI = 0x0C
RESET_MIN_MAX_FLAG_WINDSPEED_LO = 0x0D
RESET_MIN_MAX_FLAG_GUST_HI = 0x0E
RESET_MIN_MAX_FLAG_GUST_LO = 0x0F
RESET_MIN_MAX_FLAG_PRESSURE_LO = 0x10
RESET_MIN_MAX_FLAG_PRESSURE_HI = 0x11
RESET_MIN_MAX_FLAG_RAIN_1H_HI = 0x12
RESET_MIN_MAX_FLAG_RAIN_24H_HI = 0x13
RESET_MIN_MAX_FLAG_RAIN_LAST_WEEK_HI = 0x14
RESET_MIN_MAX_FLAG_RAIN_LAST_MONTH_HI = 0x15
RESET_MIN_MAX_FLAG_RAIN_TOTAL = 0x16
RESET_MIN_MAX_FLAG_INVALID = 0x17

ACTION_GET_HISTORY = 0x00
ACTION_REQ_SET_TIME = 0x01
ACTION_REQ_SET_CONFIG = 0x02
ACTION_GET_CONFIG = 0x03
ACTION_GET_CURRENT = 0x05
ACTION_SEND_CONFIG = 0x40
ACTION_SEND_TIME = 0xc0

RESPONSE_DATA_WRITTEN = 0x20
RESPONSE_GET_CONFIG = 0x40
RESPONSE_GET_CURRENT = 0x60
RESPONSE_GET_HISTORY = 0x80
RESPONSE_REQUEST = 0xa0
RESPONSE_REQ_FIRST_CONFIG = 0xa1
RESPONSE_REQ_SET_CONFIG = 0xa2
RESPONSE_REQ_SET_TIME = 0xa3

HI_01MIN = 0
HI_05MIN = 1
HI_10MIN = 2
HI_15MIN = 3
HI_20MIN = 4
HI_30MIN = 5
HI_01STD = 6
HI_02STD = 7
HI_04STD = 8
HI_06STD = 9
HI_08STD = 0xA
HI_12STD = 0xB
HI_24STD = 0xC

history_intervals = {
    HI_01MIN: 1,
    HI_05MIN: 5,
    HI_10MIN: 10,
    HI_15MIN: 15,
    HI_20MIN: 20,
    HI_30MIN: 30,
    HI_01STD: 60,
    HI_02STD: 120,
    HI_04STD: 240,
    HI_06STD: 360,
    HI_08STD: 480,
    HI_12STD: 720,
    HI_24STD: 1440,
    }

# frequency standards and their associated transmission frequencies
frequencies = {
    'US': 905000000,
    'EU': 868300000,
}


# HWPro presents battery flags as WS/TH/RAIN/WIND
# 0 - wind
# 1 - rain
# 2 - thermo-hygro
# 3 - console

batterybits = {'wind': 0, 'rain': 1, 'th': 2, 'console': 3}


def getBatteryStatus(status, flag):
    """Return 1 if bit is set, 0 otherwise"""
    bit = batterybits.get(flag)
    if bit is None:
        return None
    if BitHandling.testBit(status, bit):
        return 1
    return 0


# NP - not present
# OFL - outside factory limits
class SensorLimits:
    temperature_offset = 40.0
    temperature_NP = 81.1
    temperature_OFL = 136.0
    humidity_NP = 110.0
    humidity_OFL = 121.0
    pressure_NP = 10101010.0
    pressure_OFL = 16666.5
    rain_NP = -0.2
    rain_OFL = 16666.664
    wind_NP = 183.6  # km/h = 51.0 m/s
    wind_OFL = 183.96  # km/h = 51.099998 m/s


# NP - not present
# OFL - outside factory limits
class WeatherTraits(object):
    windDirMap = {
        0: "N", 1: "NNE", 2: "NE", 3: "ENE", 4: "E", 5: "ESE", 6: "SE",
        7: "SSE", 8: "S", 9: "SSW", 10: "SW", 11: "WSW", 12: "W",
        13: "WNW", 14: "NW", 15: "NWN", 16: "err", 17: "inv", 18: "None"}
    forecastMap = {
        0: "Rainy(Bad)", 1: "Cloudy(Neutral)", 2: "Sunny(Good)",  3: "Error"}
    trendMap = {
        0: "Stable(Neutral)", 1: "Rising(Up)", 2: "Falling(Down)", 3: "Error"}

# firmware XXX has bogus date values for these fields
_bad_labels = ['RainLastMonthMax', 'RainLastWeekMax', 'PressureRelativeMin']


def getWindDir(wdir, wspeed):
    if wspeed is None or wspeed == 0:
        return None
    if wdir < 0 or wdir >= 16:
        return None
    return wdir * 360 / 16


class Decode(object):

    @staticmethod
    def isOFL2(buf, start, start_on_hi_nibble):
        if start_on_hi_nibble:
            result = ((buf[0][start+0] >> 4) == 15 or
                      (buf[0][start+0] & 0xF) == 15)
        else:
            result = ((buf[0][start+0] & 0xF) == 15 or
                      (buf[0][start+1] >> 4) == 15)
        return result

    @staticmethod
    def isOFL3(buf, start, start_on_hi_nibble):
        if start_on_hi_nibble:
            result = ((buf[0][start+0] >> 4) == 15 or
                      (buf[0][start+0] & 0xF) == 15 or
                      (buf[0][start+1] >> 4) == 15)
        else:
            result = ((buf[0][start+0] & 0xF) == 15 or
                      (buf[0][start+1] >> 4) == 15 or
                      (buf[0][start+1] & 0xF) == 15)
        return result

    @staticmethod
    def isOFL5(buf, start, start_on_hi_nibble):
        if start_on_hi_nibble:
            result = ((buf[0][start+0] >> 4) == 15 or
                      (buf[0][start+0] & 0xF) == 15 or
                      (buf[0][start+1] >> 4) == 15 or
                      (buf[0][start+1] & 0xF) == 15 or
                      (buf[0][start+2] >> 4) == 15)
        else:
            result = ((buf[0][start+0] & 0xF) == 15 or
                      (buf[0][start+1] >> 4) == 15 or
                      (buf[0][start+1] & 0xF) == 15 or
                      (buf[0][start+2] >> 4) == 15 or
                      (buf[0][start+2] & 0xF) == 15)
        return result

    @staticmethod
    def isErr2(buf, start, start_on_hi_nibble):
        if start_on_hi_nibble:
            result = ((buf[0][start+0] >> 4) >= 10 and
                      (buf[0][start+0] >> 4) != 15 or
                      (buf[0][start+0] & 0xF) >= 10 and
                      (buf[0][start+0] & 0xF) != 15)
        else:
            result = ((buf[0][start+0] & 0xF) >= 10 and
                      (buf[0][start+0] & 0xF) != 15 or
                      (buf[0][start+1] >> 4) >= 10 and
                      (buf[0][start+1] >> 4) != 15)
        return result
        
    @staticmethod
    def isErr3(buf, start, start_on_hi_nibble):
        if start_on_hi_nibble:
            result = ((buf[0][start+0] >> 4) >= 10 and
                      (buf[0][start+0] >> 4) != 15 or
                      (buf[0][start+0] & 0xF) >= 10 and
                      (buf[0][start+0] & 0xF) != 15 or
                      (buf[0][start+1] >> 4) >= 10 and
                      (buf[0][start+1] >> 4) != 15)
        else:
            result = ((buf[0][start+0] & 0xF) >= 10 and
                      (buf[0][start+0] & 0xF) != 15 or
                      (buf[0][start+1] >> 4) >= 10 and
                      (buf[0][start+1] >> 4) != 15 or
                      (buf[0][start+1] & 0xF) >= 10 and
                      (buf[0][start+1] & 0xF) != 15)
        return result
        
    @staticmethod
    def isErr5(buf, start, start_on_hi_nibble):
        if start_on_hi_nibble:
            result = ((buf[0][start+0] >> 4) >= 10 and
                      (buf[0][start+0] >> 4) != 15 or
                      (buf[0][start+0] & 0xF) >= 10 and
                      (buf[0][start+0] & 0xF) != 15 or
                      (buf[0][start+1] >> 4) >= 10 and
                      (buf[0][start+1] >> 4) != 15 or
                      (buf[0][start+1] & 0xF) >= 10 and
                      (buf[0][start+1] & 0xF) != 15 or
                      (buf[0][start+2] >> 4) >= 10 and
                      (buf[0][start+2] >> 4) != 15)
        else:
            result = ((buf[0][start+0] & 0xF) >= 10 and
                      (buf[0][start+0] & 0xF) != 15 or
                      (buf[0][start+1] >> 4) >= 10 and
                      (buf[0][start+1] >> 4) != 15 or
                      (buf[0][start+1] & 0xF) >= 10 and
                      (buf[0][start+1] & 0xF) != 15 or
                      (buf[0][start+2] >> 4) >= 10 and
                      (buf[0][start+2] >> 4) != 15 or
                      (buf[0][start+2] & 0xF) >= 10 and
                      (buf[0][start+2] & 0xF) != 15)
        return result

    @staticmethod
    def reverseByteOrder(buf, start, count):
        nbuf = buf[0]
        for i in xrange(0, count >> 1):
            tmp = nbuf[start + i]
            nbuf[start + i] = nbuf[start + count - i - 1]
            nbuf[start + count - i - 1] = tmp
        buf[0] = nbuf

    @staticmethod
    def readWindDirectionShared(buf, start):
        return buf[0][0+start] & 0xF, buf[0][start] >> 4

    @staticmethod
    def toInt_2(buf, start, start_on_hi_nibble):
        """read 2 nibbles"""
        if start_on_hi_nibble:
            rawpre = (buf[0][start+0] >> 4) * 10 \
                + (buf[0][start+0] & 0xF) * 1
        else:
            rawpre = (buf[0][start+0] & 0xF) * 10 \
                + (buf[0][start+1] >> 4) * 1
        return rawpre

    @staticmethod
    def toRain_7_3(buf, start, start_on_hi_nibble):
        """read 7 nibbles, presentation with 3 decimals; units of mm"""
        if Decode.isErr2(buf, start+0, start_on_hi_nibble) or Decode.isErr5(buf, start+1, start_on_hi_nibble):
            result = SensorLimits.rain_NP
        elif Decode.isOFL2(buf, start+0, start_on_hi_nibble) or Decode.isOFL5(buf, start+1, start_on_hi_nibble):
            result = SensorLimits.rain_OFL
        elif start_on_hi_nibble:
            result = ((buf[0][start+0] >> 4) * 1000 +
                      (buf[0][start+0] & 0xF) * 100 +
                      (buf[0][start+1] >> 4) * 10 +
                      (buf[0][start+1] & 0xF) * 1 +
                      (buf[0][start+2] >> 4) * 0.1 +
                      (buf[0][start+2] & 0xF) * 0.01 +
                      (buf[0][start+3] >> 4) * 0.001)
        else:
            result = ((buf[0][start+0] & 0xF) * 1000 +
                      (buf[0][start+1] >> 4) * 100 +
                      (buf[0][start+1] & 0xF) * 10 +
                      (buf[0][start+2] >> 4) * 1 +
                      (buf[0][start+2] & 0xF) * 0.1 +
                      (buf[0][start+3] >> 4) * 0.01 +
                      (buf[0][start+3] & 0xF) * 0.001)
        return result

    @staticmethod
    def toRain_6_2(buf, start, start_on_hi_nibble):
        """read 6 nibbles, presentation with 2 decimals; units of mm"""
        if (Decode.isErr2(buf, start+0, start_on_hi_nibble) or
                Decode.isErr2(buf, start+1, start_on_hi_nibble) or
                Decode.isErr2(buf, start+2, start_on_hi_nibble)):
            result = SensorLimits.rain_NP
        elif (Decode.isOFL2(buf, start+0, start_on_hi_nibble) or
                Decode.isOFL2(buf, start+1, start_on_hi_nibble) or
                Decode.isOFL2(buf, start+2, start_on_hi_nibble)):
            result = SensorLimits.rain_OFL
        elif start_on_hi_nibble:
            result = ((buf[0][start+0] >> 4) * 1000 +
                      (buf[0][start+0] & 0xF) * 100 +
                      (buf[0][start+1] >> 4) * 10 +
                      (buf[0][start+1] & 0xF) * 1 +
                      (buf[0][start+2] >> 4) * 0.1 +
                      (buf[0][start+2] & 0xF) * 0.01)
        else:
            result = ((buf[0][start+0] & 0xF) * 1000 +
                      (buf[0][start+1] >> 4) * 100 +
                      (buf[0][start+1] & 0xF) * 10 +
                      (buf[0][start+2] >> 4) * 1 +
                      (buf[0][start+2] & 0xF) * 0.1 +
                      (buf[0][start+3] >> 4) * 0.01)
        return result

    @staticmethod
    def toRain_3_1(buf, start, start_on_hi_nibble):
        """read 3 nibbles, presentation with 1 decimal; units of 0.1 inch"""
        if start_on_hi_nibble:
            hibyte = buf[0][start+0]
            lobyte = (buf[0][start+1] >> 4) & 0xF
        else:
            hibyte = 16*(buf[0][start+0] & 0xF) + ((buf[0][start+1] >> 4) & 0xF)
            lobyte = buf[0][start+1] & 0xF            
        if hibyte == 0xFF and lobyte == 0xE:
            result = SensorLimits.rain_NP
        elif hibyte == 0xFF and lobyte == 0xF:
            result = SensorLimits.rain_OFL
        else:
            val = Decode.toFloat_3_1(buf, start, start_on_hi_nibble)  # 0.1 inch
            result = val * 2.54  # mm
        return result

    @staticmethod  
    def toFloat_3_1(buf, start, start_on_hi_nibble):
        """read 3 nibbles, presentation with 1 decimal"""
        if start_on_hi_nibble:
            result = (buf[0][start+0] >> 4) * 16**2 \
                + (buf[0][start+0] & 0xF) * 16**1 \
                + (buf[0][start+1] >> 4) * 16**0
        else:
            result = (buf[0][start+0] & 0xF) * 16**2 \
                + (buf[0][start+1] >> 4) * 16**1 \
                + (buf[0][start+1] & 0xF) * 16**0
        result /= 10.0
        return result

    @staticmethod
    def toDateTime(buf, start, start_on_hi_nibble, label):
        """read 10 nibbles, presentation as DateTime"""
        result = None
        if (Decode.isErr2(buf, start+0, start_on_hi_nibble) or
                Decode.isErr2(buf, start+1, start_on_hi_nibble) or
                Decode.isErr2(buf, start+2, start_on_hi_nibble) or
                Decode.isErr2(buf, start+3, start_on_hi_nibble) or
                Decode.isErr2(buf, start+4, start_on_hi_nibble)):
            logerr('ToDateTime: bogus date for %s: error status in buffer' %
                   label)
        else:
            year = Decode.toInt_2(buf, start+0, start_on_hi_nibble) + 2000
            month = Decode.toInt_2(buf, start+1, start_on_hi_nibble)
            days = Decode.toInt_2(buf, start+2, start_on_hi_nibble)
            hours = Decode.toInt_2(buf, start+3, start_on_hi_nibble)
            minutes = Decode.toInt_2(buf, start+4, start_on_hi_nibble)
            try:
                result = datetime(year, month, days, hours, minutes)
            except ValueError:
                if label not in _bad_labels:
                    logerr(('ToDateTime: bogus date for %s:'
                            ' bad date conversion from'
                            ' %s %s %s %s %s') %
                           (label, minutes, hours, days, month, year))
        if result is None:
            # FIXME: use None instead of a really old date to indicate invalid
            result = datetime(1900, 01, 01, 00, 00)
        return result

    @staticmethod
    def toHumidity_2_0(buf, start, start_on_hi_nibble):
        """read 2 nibbles, presentation with 0 decimal"""
        if Decode.isErr2(buf, start+0, start_on_hi_nibble):
            result = SensorLimits.humidity_NP
        elif Decode.isOFL2(buf, start+0, start_on_hi_nibble):
            result = SensorLimits.humidity_OFL
        else:
            result = Decode.toInt_2(buf, start, start_on_hi_nibble)
        return result

    @staticmethod
    def toTemperature_5_3(buf, start, start_on_hi_nibble):
        """read 5 nibbles, presentation with 3 decimals; units of degree C"""
        if Decode.isErr5(buf, start+0, start_on_hi_nibble):
            result = SensorLimits.temperature_NP
        elif Decode.isOFL5(buf, start+0, start_on_hi_nibble):
            result = SensorLimits.temperature_OFL
        else:
            if start_on_hi_nibble:
                rawtemp = ((buf[0][start+0] >> 4) * 10 +
                           (buf[0][start+0] & 0xF) * 1 +
                           (buf[0][start+1] >> 4) * 0.1 +
                           (buf[0][start+1] & 0xF) * 0.01 +
                           (buf[0][start+2] >> 4) * 0.001)
            else:
                rawtemp = ((buf[0][start+0] & 0xF) * 10 +
                           (buf[0][start+1] >> 4) * 1 +
                           (buf[0][start+1] & 0xF) * 0.1 +
                           (buf[0][start+2] >> 4) * 0.01 +
                           (buf[0][start+2] & 0xF) * 0.001)
            result = rawtemp - SensorLimits.temperature_offset
        return result

    @staticmethod
    def toTemperature_3_1(buf, start, start_on_hi_nibble):
        """read 3 nibbles, presentation with 1 decimal; units of degree C"""
        if Decode.isErr3(buf, start+0, start_on_hi_nibble):
            result = SensorLimits.temperature_NP
        elif Decode.isOFL3(buf, start+0, start_on_hi_nibble):
            result = SensorLimits.temperature_OFL
        else:
            if start_on_hi_nibble:
                rawtemp = ((buf[0][start+0] >> 4) * 10 +
                           (buf[0][start+0] & 0xF) * 1 +
                           (buf[0][start+1] >> 4) * 0.1)
            else:
                rawtemp = ((buf[0][start+0] & 0xF) * 10 +
                           (buf[0][start+1] >> 4) * 1 +
                           (buf[0][start+1] & 0xF) * 0.1)
            result = rawtemp - SensorLimits.temperature_offset
        return result

    @staticmethod
    def toWindspeed_6_2(buf, start):
        """read 6 nibbles, presentation with 2 decimals; units of km/h"""
        result = ((buf[0][start+0] >> 4) * 16**5 +
                  (buf[0][start+0] & 0xF) * 16**4 +
                  (buf[0][start+1] >> 4) * 16**3 +
                  (buf[0][start+1] & 0xF) * 16**2 +
                  (buf[0][start+2] >> 4) * 16**1 +
                  (buf[0][start+2] & 0xF))
        result /= 256.0
        result /= 100.0  # km/h
        return result

    @staticmethod
    def toWindspeed_3_1(buf, start, start_on_hi_nibble):
        """read 3 nibbles, presentation with 1 decimal; units of m/s"""
        if start_on_hi_nibble:
            hibyte = buf[0][start+0]
            lobyte = (buf[0][start+1] >> 4) & 0xF
        else:
            hibyte = 16*(buf[0][start+0] & 0xF) + ((buf[0][start+1] >> 4) & 0xF)
            lobyte = buf[0][start+1] & 0xF            
        if hibyte == 0xFF and lobyte == 0xE:
            result = SensorLimits.wind_NP
        elif hibyte == 0xFF and lobyte == 0xF:
            result = SensorLimits.wind_OFL
        else:
            result = Decode.toFloat_3_1(buf, start, start_on_hi_nibble)  # m/s
            result *= 3.6  # km/h
        return result

    @staticmethod
    def readPressureShared(buf, start, start_on_hi_nibble):
        return (Decode.toPressure_hPa_5_1(buf, start+2, 1-start_on_hi_nibble),
                Decode.toPressure_inHg_5_2(buf, start, start_on_hi_nibble))

    @staticmethod
    def toPressure_hPa_5_1(buf, start, start_on_hi_nibble):
        """read 5 nibbles, presentation with 1 decimal; units of hPa (mbar)"""
        if Decode.isErr5(buf, start+0, start_on_hi_nibble):
            result = SensorLimits.pressure_NP
        elif Decode.isOFL5(buf, start+0, start_on_hi_nibble):
            result = SensorLimits.pressure_OFL
        elif start_on_hi_nibble:
            result = (buf[0][start+0] >> 4) * 1000 \
                + (buf[0][start+0] & 0xF) * 100  \
                + (buf[0][start+1] >> 4) * 10  \
                + (buf[0][start+1] & 0xF) * 1   \
                + (buf[0][start+2] >> 4) * 0.1
        else:
            result = (buf[0][start+0] & 0xF) * 1000 \
                + (buf[0][start+1] >> 4) * 100  \
                + (buf[0][start+1] & 0xF) * 10  \
                + (buf[0][start+2] >> 4) * 1   \
                + (buf[0][start+2] & 0xF) * 0.1
        return result

    @staticmethod
    def toPressure_inHg_5_2(buf, start, start_on_hi_nibble):
        """read 5 nibbles, presentation with 2 decimals; units of inHg"""
        if Decode.isErr5(buf, start+0, start_on_hi_nibble):
            result = SensorLimits.pressure_NP
        elif Decode.isOFL5(buf, start+0, start_on_hi_nibble):
            result = SensorLimits.pressure_OFL
        elif start_on_hi_nibble:
            result = (buf[0][start+0] >> 4) * 100 \
                + (buf[0][start+0] & 0xF) * 10   \
                + (buf[0][start+1] >> 4) * 1   \
                + (buf[0][start+1] & 0xF) * 0.1 \
                + (buf[0][start+2] >> 4) * 0.01
        else:
            result = (buf[0][start+0] & 0xF) * 100 \
                + (buf[0][start+1] >> 4) * 10   \
                + (buf[0][start+1] & 0xF) * 1   \
                + (buf[0][start+2] >> 4) * 0.1 \
                + (buf[0][start+2] & 0xF) * 0.01
        return result


class CurrentData(object):

    def __init__(self):
        self.timestamp = None
        self.checksum = None
        self.PressureRelative_hPa = SensorLimits.pressure_NP
        self.PressureRelative_hPaMin = SensorLimits.pressure_NP
        self.PressureRelative_hPaMax = SensorLimits.pressure_NP
        self.PressureRelative_inHg = SensorLimits.pressure_NP
        self.PressureRelative_inHgMin = SensorLimits.pressure_NP
        self.PressureRelative_inHgMax = SensorLimits.pressure_NP
        self.WindSpeed = SensorLimits.wind_NP
        self.WindDirection = WIND_DIRECTION_NONE
        self.WindDirection1 = WIND_DIRECTION_NONE
        self.WindDirection2 = WIND_DIRECTION_NONE
        self.WindDirection3 = WIND_DIRECTION_NONE
        self.WindDirection4 = WIND_DIRECTION_NONE
        self.WindDirection5 = WIND_DIRECTION_NONE
        self.Gust = SensorLimits.wind_NP
        self.GustMax = SensorLimits.wind_NP
        self.GustDirection = WIND_DIRECTION_NONE
        self.GustDirection1 = WIND_DIRECTION_NONE
        self.GustDirection2 = WIND_DIRECTION_NONE
        self.GustDirection3 = WIND_DIRECTION_NONE
        self.GustDirection4 = WIND_DIRECTION_NONE
        self.GustDirection5 = WIND_DIRECTION_NONE
        self.Rain1H = SensorLimits.rain_NP
        self.Rain1HMax = SensorLimits.rain_NP
        self.Rain24H = SensorLimits.rain_NP
        self.Rain24HMax = SensorLimits.rain_NP
        self.RainLastWeek = SensorLimits.rain_NP
        self.RainLastWeekMax = SensorLimits.rain_NP
        self.RainLastMonth = SensorLimits.rain_NP
        self.RainLastMonthMax = SensorLimits.rain_NP
        self.RainTotal = SensorLimits.rain_NP
        self.LastRainReset = None
        self.TempIndoor = SensorLimits.temperature_NP
        self.TempIndoorMin = SensorLimits.temperature_NP
        self.TempIndoorMax = SensorLimits.temperature_NP
        self.TempOutdoor = SensorLimits.temperature_NP
        self.TempOutdoorMin = SensorLimits.temperature_NP
        self.TempOutdoorMax = SensorLimits.temperature_NP
        self.HumidityIndoor = SensorLimits.humidity_NP
        self.HumidityIndoorMin = SensorLimits.humidity_NP
        self.HumidityIndoorMax = SensorLimits.humidity_NP
        self.HumidityOutdoor = SensorLimits.humidity_NP
        self.HumidityOutdoorMin = SensorLimits.humidity_NP
        self.HumidityOutdoorMax = SensorLimits.humidity_NP
        self.Dewpoint = SensorLimits.temperature_NP
        self.DewpointMin = SensorLimits.temperature_NP
        self.DewpointMax = SensorLimits.temperature_NP
        self.Windchill = SensorLimits.temperature_NP
        self.WindchillMin = SensorLimits.temperature_NP
        self.WindchillMax = SensorLimits.temperature_NP
        self.WeatherState = WEATHER_ERR
        self.WeatherTendency = TREND_ERR
        self.AlarmRingingFlags = 0
        self.AlarmMarkedFlags = 0
        self.PresRel_hPMax = 0.0
        self.PresRel_inHMax = 0.0

    @staticmethod
    def calcChecksum(buf):
        return calc_checksum(buf, 6)

    def checksum(self):
        return self.checksum

    def read(self, buf):
        self.timestamp = int(time.time() + 0.5)
        if DEBUG_WEATHER_DATA > 0:
            logdbg('Read weather data; ts=%s' % self.timestamp)
        self.checksum = CurrentData.calcChecksum(buf)

        nbuf = [0]
        nbuf[0] = buf[0]
        self.StartBytes = nbuf[0][6]*0xF + nbuf[0][7]  # FIXME: what is this?
        self.WeatherTendency = (nbuf[0][8] >> 4) & 0xF
        if self.WeatherTendency > 3:
            self.WeatherTendency = 3 
        self.WeatherState = nbuf[0][8] & 0xF
        if self.WeatherState > 3:
            self.WeatherState = 3 

        self.TempIndoorMax = Decode.toTemperature_5_3(nbuf, 19, 0)
        self.TempIndoorMin = Decode.toTemperature_5_3(nbuf, 22, 1)
        self.TempIndoor = Decode.toTemperature_5_3(nbuf, 24, 0)
        self.TempIndoorMaxDT = (None
                                if self.TempIndoorMax == SensorLimits.temperature_NP or
                                   self.TempIndoorMax == SensorLimits.temperature_OFL
                                else Decode.toDateTime(nbuf, 9, 0, 'TempIndoorMax'))
        self.TempIndoorMinDT = (None
                                if self.TempIndoorMin == SensorLimits.temperature_NP or
                                   self.TempIndoorMin == SensorLimits.temperature_OFL
                                else Decode.toDateTime(nbuf, 14, 0, 'TempIndoorMin'))

        self.TempOutdoorMax = Decode.toTemperature_5_3(nbuf, 37, 0)
        self.TempOutdoorMin = Decode.toTemperature_5_3(nbuf, 40, 1)
        self.TempOutdoor = Decode.toTemperature_5_3(nbuf, 42, 0)
        self.TempOutdoorMaxDT = (None
                                 if self.TempOutdoorMax == SensorLimits.temperature_NP or
                                    self.TempOutdoorMax == SensorLimits.temperature_OFL
                                 else Decode.toDateTime(nbuf, 27, 0, 'TempOutdoorMax'))
        self.TempOutdoorMinDT = (None
                                 if self.TempOutdoorMin == SensorLimits.temperature_NP or
                                    self.TempOutdoorMin == SensorLimits.temperature_OFL
                                 else Decode.toDateTime(nbuf, 32, 0, 'TempOutdoorMin'))

        self.WindchillMax = Decode.toTemperature_5_3(nbuf, 55, 0)
        self.WindchillMin = Decode.toTemperature_5_3(nbuf, 58, 1)
        self.Windchill = Decode.toTemperature_5_3(nbuf, 60, 0)
        self.WindchillMaxDT = (None
                               if self.WindchillMax == SensorLimits.temperature_NP or
                                  self.WindchillMax == SensorLimits.temperature_OFL
                               else Decode.toDateTime(nbuf, 45, 0, 'WindchillMax'))
        self.WindchillMinDT = (None
                               if self.WindchillMin == SensorLimits.temperature_NP or
                                  self.WindchillMin == SensorLimits.temperature_OFL
                               else Decode.toDateTime(nbuf, 50, 0, 'WindchillMin'))

        self.DewpointMax = Decode.toTemperature_5_3(nbuf, 73, 0)
        self.DewpointMin = Decode.toTemperature_5_3(nbuf, 76, 1)
        self.Dewpoint = Decode.toTemperature_5_3(nbuf, 78, 0)
        self.DewpointMinDT = (None
                              if self.DewpointMin == SensorLimits.temperature_NP or
                                 self.DewpointMin == SensorLimits.temperature_OFL
                              else Decode.toDateTime(nbuf, 68, 0, 'DewpointMin'))
        self.DewpointMaxDT = (None
                              if self.DewpointMax == SensorLimits.temperature_NP or
                                 self.DewpointMax == SensorLimits.temperature_OFL
                              else Decode.toDateTime(nbuf, 63, 0, 'DewpointMax'))

        self.HumidityIndoorMax = Decode.toHumidity_2_0(nbuf, 91, 1)
        self.HumidityIndoorMin = Decode.toHumidity_2_0(nbuf, 92, 1)
        self.HumidityIndoor = Decode.toHumidity_2_0(nbuf, 93, 1)
        self.HumidityIndoorMaxDT = (None
                                    if self.HumidityIndoorMax == SensorLimits.humidity_NP or
                                       self.HumidityIndoorMax == SensorLimits.humidity_OFL
                                    else Decode.toDateTime(nbuf, 81, 1, 'HumidityIndoorMax'))
        self.HumidityIndoorMinDT = (None
                                    if self.HumidityIndoorMin == SensorLimits.humidity_NP or
                                       self.HumidityIndoorMin == SensorLimits.humidity_OFL
                                    else Decode.toDateTime(nbuf, 86, 1, 'HumidityIndoorMin'))

        self.HumidityOutdoorMax = Decode.toHumidity_2_0(nbuf, 104, 1)
        self.HumidityOutdoorMin = Decode.toHumidity_2_0(nbuf, 105, 1)
        self.HumidityOutdoor = Decode.toHumidity_2_0(nbuf, 106, 1)
        self.HumidityOutdoorMaxDT = (None
                                     if self.HumidityOutdoorMax == SensorLimits.humidity_NP or
                                        self.HumidityOutdoorMax == SensorLimits.humidity_OFL
                                     else Decode.toDateTime(nbuf, 94, 1, 'HumidityOutdoorMax'))
        self.HumidityOutdoorMinDT = (None
                                     if self.HumidityOutdoorMin == SensorLimits.humidity_NP or
                                        self.HumidityOutdoorMin == SensorLimits.humidity_OFL
                                     else Decode.toDateTime(nbuf, 99, 1, 'HumidityOutdoorMin'))

        self.RainLastMonthMaxDT = Decode.toDateTime(nbuf, 107, 1, 'RainLastMonthMax')
        self.RainLastMonthMax = Decode.toRain_6_2(nbuf, 112, 1)
        self.RainLastMonth = Decode.toRain_6_2(nbuf, 115, 1)

        self.RainLastWeekMaxDT = Decode.toDateTime(nbuf, 118, 1, 'RainLastWeekMax')
        self.RainLastWeekMax = Decode.toRain_6_2(nbuf, 123, 1)
        self.RainLastWeek = Decode.toRain_6_2(nbuf, 126, 1)

        self.Rain24HMaxDT = Decode.toDateTime(nbuf, 129, 1, 'Rain24HMax')
        self.Rain24HMax = Decode.toRain_6_2(nbuf, 134, 1)
        self.Rain24H = Decode.toRain_6_2(nbuf, 137, 1)
        
        self.Rain1HMaxDT = Decode.toDateTime(nbuf, 140, 1, 'Rain1HMax')
        self.Rain1HMax = Decode.toRain_6_2(nbuf, 145, 1)
        self.Rain1H = Decode.toRain_6_2(nbuf, 148, 1)

        self.LastRainReset = Decode.toDateTime(nbuf, 151, 0, 'LastRainReset')
        self.RainTotal = Decode.toRain_7_3(nbuf, 156, 0)

        (w, w1) = Decode.readWindDirectionShared(nbuf, 162)
        (w2, w3) = Decode.readWindDirectionShared(nbuf, 161)
        (w4, w5) = Decode.readWindDirectionShared(nbuf, 160)
        self.WindDirection = w
        self.WindDirection1 = w1
        self.WindDirection2 = w2
        self.WindDirection3 = w3
        self.WindDirection4 = w4
        self.WindDirection5 = w5

        if DEBUG_WEATHER_DATA > 2:
            unknownbuf = [0] * 9
            for i in xrange(0, 9):
                unknownbuf[i] = nbuf[163+i]
            strbuf = ""
            for i in unknownbuf:
                strbuf += str("%.2x " % i)
            logdbg('Bytes with unknown meaning at 157-165: %s' % strbuf)

        self.WindSpeed = Decode.toWindspeed_6_2(nbuf, 172)

        # FIXME: read the WindErrFlags
        (g, g1) = Decode.readWindDirectionShared(nbuf, 177)
        (g2, g3) = Decode.readWindDirectionShared(nbuf, 176)
        (g4, g5) = Decode.readWindDirectionShared(nbuf, 175)
        self.GustDirection = g
        self.GustDirection1 = g1
        self.GustDirection2 = g2
        self.GustDirection3 = g3
        self.GustDirection4 = g4
        self.GustDirection5 = g5

        self.GustMax = Decode.toWindspeed_6_2(nbuf, 184)
        self.GustMaxDT = (None
                          if self.GustMax == SensorLimits.wind_NP or
                             self.GustMax == SensorLimits.wind_OFL
                          else Decode.toDateTime(nbuf, 179, 1, 'GustMax'))
        self.Gust = Decode.toWindspeed_6_2(nbuf, 187)

        # Apparently the station returns only ONE date time for both hPa/inHg
        # Min Time Reset and Max Time Reset
        self.PressureRelative_hPaMaxDT = Decode.toDateTime(nbuf, 190, 1, 'PressureRelative_hPaMax')
        self.PressureRelative_inHgMaxDT = self.PressureRelative_hPaMaxDT
        # firmware bug, should be: Decode.toDateTime(nbuf, 195, 1)
        self.PressureRelative_hPaMinDT = self.PressureRelative_hPaMaxDT
        self.PressureRelative_inHgMinDT = self.PressureRelative_hPaMinDT        
        # firmware bug, should be: self.PressureRelative_hPaMinDT
        (self.PresRel_hPMax, self.PresRel_inHMax) = Decode.readPressureShared(nbuf, 195, 1)
        (self.PressureRelative_hPaMax, self.PressureRelative_inHgMax) = Decode.readPressureShared(nbuf, 200, 1)
        (self.PressureRelative_hPaMin, self.PressureRelative_inHgMin) = Decode.readPressureShared(nbuf, 205, 1)
        (self.PressureRelative_hPa, self.PressureRelative_inHg) = Decode.readPressureShared(nbuf, 210, 1)

    def toLog(self):
        logdbg("WeatherState=%s WeatherTendency=%s AlarmRingingFlags %04x" %
               (WeatherTraits.forecastMap[self.WeatherState],
                WeatherTraits.trendMap[self.WeatherTendency],
                self.AlarmRingingFlags))
        logdbg("TempIndoor=     %8.3f Min=%8.3f (%s) Max=%8.3f (%s)" %
               (self.TempIndoor, self.TempIndoorMin,
                self.TempIndoorMinDT, self.TempIndoorMax,
                self.TempIndoorMaxDT))
        logdbg("HumidityIndoor= %8.3f Min=%8.3f (%s) Max=%8.3f (%s)" %
               (self.HumidityIndoor,
                self.HumidityIndoorMin,
                self.HumidityIndoorMinDT,
                self.HumidityIndoorMax,
                self.HumidityIndoorMaxDT))
        logdbg("TempOutdoor=    %8.3f Min=%8.3f (%s) Max=%8.3f (%s)" %
               (self.TempOutdoor,
                self.TempOutdoorMin,
                self.TempOutdoorMinDT,
                self.TempOutdoorMax,
                self.TempOutdoorMaxDT))
        logdbg("HumidityOutdoor=%8.3f Min=%8.3f (%s) Max=%8.3f (%s)" %
               (self.HumidityOutdoor,
                self.HumidityOutdoorMin,
                self.HumidityOutdoorMinDT,
                self.HumidityOutdoorMax,
                self.HumidityOutdoorMaxDT))
        logdbg("Windchill=      %8.3f Min=%8.3f (%s) Max=%8.3f (%s)" %
               (self.Windchill,
                self.WindchillMin,
                self.WindchillMinDT,
                self.WindchillMax,
                self.WindchillMaxDT))
        logdbg("Dewpoint=       %8.3f Min=%8.3f (%s) Max=%8.3f (%s)" %
               (self.Dewpoint,
                self.DewpointMin,
                self.DewpointMinDT,
                self.DewpointMax,
                self.DewpointMaxDT))
        logdbg("WindSpeed=      %8.3f" % self.WindSpeed)
        logdbg("Gust=           %8.3f                                     Max=%8.3f (%s)" %
               (self.Gust,
                self.GustMax,
                self.GustMaxDT))
        logdbg('WindDirection=    %3s    GustDirection=    %3s' %
               (WeatherTraits.windDirMap[self.WindDirection],
                WeatherTraits.windDirMap[self.GustDirection]))
        logdbg('WindDirection1=   %3s    GustDirection1=   %3s' %
               (WeatherTraits.windDirMap[self.WindDirection1],
                WeatherTraits.windDirMap[self.GustDirection1]))
        logdbg('WindDirection2=   %3s    GustDirection2=   %3s' %
               (WeatherTraits.windDirMap[self.WindDirection2],
                WeatherTraits.windDirMap[self.GustDirection2]))
        logdbg('WindDirection3=   %3s    GustDirection3=   %3s' %
               (WeatherTraits.windDirMap[self.WindDirection3],
                WeatherTraits.windDirMap[self.GustDirection3]))
        logdbg('WindDirection4=   %3s    GustDirection4=   %3s' %
               (WeatherTraits.windDirMap[self.WindDirection4],
                WeatherTraits.windDirMap[self.GustDirection4]))
        logdbg('WindDirection5=   %3s    GustDirection5=   %3s' %
               (WeatherTraits.windDirMap[self.WindDirection5],
                WeatherTraits.windDirMap[self.GustDirection5]))
        if (self.RainLastMonth > 0) or (self.RainLastWeek > 0):
            logdbg("RainLastMonth=  %8.3f                                     Max=%8.3f (%s)" %
                   (self.RainLastMonth,
                    self.RainLastMonthMax,
                    self.RainLastMonthMaxDT))
            logdbg("RainLastWeek=   %8.3f                                     Max=%8.3f (%s)" %
                   (self.RainLastWeek,
                    self.RainLastWeekMax,
                    self.RainLastWeekMaxDT))
        logdbg("Rain24H=        %8.3f                                     Max=%8.3f (%s)" %
               (self.Rain24H,
                self.Rain24HMax,
                self.Rain24HMaxDT))
        logdbg("Rain1H=         %8.3f                                     Max=%8.3f (%s)" %
               (self.Rain1H,
                self.Rain1HMax,
                self.Rain1HMaxDT))
        logdbg("RainTotal=      %8.3f                            LastRainReset=         (%s)" %
               (self.RainTotal,
                self.LastRainReset))
        logdbg("PressureRel_hPa= %8.3f Min=%8.3f (%s) Max=%8.3f (%s) " %
               (self.PressureRelative_hPa,
                self.PressureRelative_hPaMin,
                self.PressureRelative_hPaMinDT,
                self.PressureRelative_hPaMax,
                self.PressureRelative_hPaMaxDT))
        logdbg("PressureRel_inHg=%8.3f Min=%8.3f (%s) Max=%8.3f (%s) " %
               (self.PressureRelative_inHg,
                self.PressureRelative_inHgMin,
                self.PressureRelative_inHgMinDT,
                self.PressureRelative_inHgMax,
                self.PressureRelative_inHgMaxDT))
        # logdbg('(* Bug in Weather Station: PressureRelative.MinDT is written to location of PressureRelativeDT')
        # logdbg('Instead of PressureRelative.MinDT we get: _PresRel_hPMax= %8.3f, _PresRel_inHg_max =%8.3f;' %
        # (self.PresRel_hPMax, self.PresRel_inHMax))


class StationConfig(object):

    def __init__(self):
        self.InBufCS = 0  # checksum of received config
        self.OutBufCS = 0  # calculated config checksum from outbuf config
        self.ClockMode = 0
        self.TemperatureFormat = 0
        self.pressure_format = 0
        self.rain_format = 0
        self.WindspeedFormat = 0
        self.WeatherThreshold = 0
        self.StormThreshold = 0
        self.LCDContrast = 0
        self.LowBatFlags = 0
        self.WindDirAlarmFlags = 0
        self.OtherAlarmFlags = 0
        self.ResetMinMaxFlags = 0  # output only
        self.HistoryInterval = 0
        self.TempIndoorMin = SensorLimits.temperature_NP
        self.TempIndoorMax = SensorLimits.temperature_NP
        self.TempOutdoorMin = SensorLimits.temperature_NP
        self.TempOutdoorMax = SensorLimits.temperature_NP
        self.HumidityIndoorMin = SensorLimits.temperature_NP
        self.HumidityIndoorMax = SensorLimits.temperature_NP
        self.HumidityOutdoorMin = SensorLimits.temperature_NP
        self.HumidityOutdoorMax = SensorLimits.temperature_NP
        self.Rain24HMax = SensorLimits.rain_NP
        self.GustMax = SensorLimits.wind_NP
        self.PressureRelative_hPaMin = SensorLimits.pressure_NP
        self.PressureRelative_hPaMax = SensorLimits.pressure_NP
        self.PressureRelative_inHgMin = SensorLimits.pressure_NP
        self.PressureRelative_inHgMax = SensorLimits.pressure_NP

    def setTemps(self, temp_format, in_temp_lo, in_temp_hi, out_temp_lo, out_temp_hi):
        f1 = temp_format
        t1 = in_temp_lo
        t2 = in_temp_hi
        t3 = out_temp_lo
        t4 = out_temp_hi
        if f1 not in [TEMPERATURE_FORMAT_FAHRENHEIT,
                      TEMPERATURE_FORMAT_CELSIUS]:
            logerr('setTemps: unknown temperature format %s' % temp_format)
            return 0
        if t1 < -40.0 or t1 > 59.9 or t2 < -40.0 or t2 > 59.9 or \
                t3 < -40.0 or t3 > 59.9 or t4 < -40.0 or t4 > 59.9:
            logerr('setTemps: one or more values out of range')
            return 0
        self.TemperatureFormat = f1
        self.TempIndoorMin = t1
        self.TempIndoorMax = t2
        self.TempOutdoorMin = t3
        self.TempOutdoorMax = t4
        return 1     
    
    def setHums(self, in_hum_lo, in_hum_hi, out_hum_lo, out_hum_hi):
        h1 = in_hum_lo
        h2 = in_hum_hi
        h3 = out_hum_lo
        h4 = out_hum_hi
        if h1 < 1 or h1 > 99 or h2 < 1 or h2 > 99 or \
                h3 < 1 or h3 > 99 or h4 < 1 or h4 > 99:
            logerr('setHums: one or more values out of range')
            return 0
        self.HumidityIndoorMin = h1
        self.HumidityIndoorMax = h2
        self.HumidityOutdoorMin = h3
        self.HumidityOutdoorMax = h4
        return 1
    
    def setRain24H(self, rain_format, rain_24h_hi):
        f1 = rain_format
        r1 = rain_24h_hi 
        if f1 not in [RAIN_FORMAT_MM, RAIN_FORMAT_INCH]:
            logerr('setRain24: unknown format %s' % rain_format)
            return 0
        if r1 < 0.0 or r1 > 9999.9:
            logerr('setRain24: value outside range')
            return 0
        self.rain_format = f1
        self.Rain24HMax = r1
        return 1
    
    def setGust(self, wind_speed_format, gust_hi):
        # When the units of a max gust alarm are changed in the weather
        # station itself, automatically the value is converted to the new
        # unit and rounded to a whole number.  Weewx receives a value
        # converted to km/h.
        #
        # It is too much trouble to sort out what exactly the internal
        # conversion algoritms are for the other wind units.
        #
        # Setting a value in km/h units is tested and works, so this will
        # be the only option available.  
        f1 = wind_speed_format
        g1 = gust_hi
        if f1 < WINDSPEED_FORMAT_MS or f1 > WINDSPEED_FORMAT_MPH:
            logerr('setGust: unknown format %s' % wind_speed_format)
            return 0
        if f1 != WINDSPEED_FORMAT_KMH:
            logerr('setGust: only units of km/h are supported')
            return 0
        if g1 < 0.0 or g1 > 180.0:
            logerr('setGust: value outside range')
            return 0 
        self.wind_speed_format = f1
        self.GustMax = int(g1)  # apparently gust value is always an integer
        return 1
    
    def setPresRels(self, pressure_format, pres_rel_hpa_lo, pres_rel_hpa_hi, pres_rel_inhg_lo, pres_rel_inhg_hi):
        f1 = pressure_format
        p1 = pres_rel_hpa_lo
        p2 = pres_rel_hpa_hi
        p3 = pres_rel_inhg_lo
        p4 = pres_rel_inhg_hi
        if f1 not in [PRESSURE_FORMAT_INHG, PRESSURE_FORMAT_HPA]:
            logerr('setPresRel: unknown format %s' % pressure_format)
            return 0
        if p1 < 920.0 or p1 > 1080.0 or p2 < 920.0 or p2 > 1080.0 or \
                p3 < 27.10 or p3 > 31.90 or p4 < 27.10 or p4 > 31.90:
            logerr('setPresRel: value outside range')
            return 0
        self.rain_format = f1
        self.PressureRelative_hPaMin = p1
        self.PressureRelative_hPaMax = p2
        self.PressureRelative_inHgMin = p3
        self.PressureRelative_inHgMax = p4
        return 1
    
    def getOutBufCS(self):
        return self.OutBufCS
             
    def getInBufCS(self):
        return self.InBufCS
    
    def setResetMinMaxFlags(self, reset_min_max_flags):
        logdbg('setResetMinMaxFlags: %s' % reset_min_max_flags)
        self.ResetMinMaxFlags = reset_min_max_flags

    @staticmethod
    def parseRain_3(number, buf, start, start_on_hi_nibble, numbytes):
        """Parse 7-digit number with 3 decimals"""
        num = int(number*1000)
        parsebuf = [0]*7
        for i in xrange(7-numbytes, 7):
            parsebuf[i] = num % 10
            num //= 10
        if start_on_hi_nibble:
                buf[0][0+start] = parsebuf[6]*16 + parsebuf[5]
                buf[0][1+start] = parsebuf[4]*16 + parsebuf[3]
                buf[0][2+start] = parsebuf[2]*16 + parsebuf[1]
                buf[0][3+start] = parsebuf[0]*16 + (buf[0][3+start] & 0xF)
        else:
                buf[0][0+start] = (buf[0][0+start] & 0xF0) + parsebuf[6]
                buf[0][1+start] = parsebuf[5]*16 + parsebuf[4]
                buf[0][2+start] = parsebuf[3]*16 + parsebuf[2]
                buf[0][3+start] = parsebuf[1]*16 + parsebuf[0]
                        
    @staticmethod
    def parseWind_6(number, buf, start):
        """Parse float number to 6 bytes"""
        num = int(number*100*256)
        parsebuf = [0] * 6
        for i in xrange(0, 6):
            parsebuf[i] = num % 16
            num //= 16
        buf[0][0+start] = parsebuf[5]*16 + parsebuf[4]
        buf[0][1+start] = parsebuf[3]*16 + parsebuf[2]
        buf[0][2+start] = parsebuf[1]*16 + parsebuf[0]
        
    @staticmethod
    def parse_0(number, buf, start, start_on_hi_nibble, numbytes):
        """Parse 5-digit number with 0 decimals"""
        num = int(number)
        nbuf = [0] * 5
        for i in xrange(5-numbytes, 5):
            nbuf[i] = num % 10
            num //= 10
        if start_on_hi_nibble:
            buf[0][0+start] = nbuf[4]*16 + nbuf[3]
            buf[0][1+start] = nbuf[2]*16 + nbuf[1]
            buf[0][2+start] = nbuf[0]*16 + (buf[0][2+start] & 0x0F)
        else:
            buf[0][0+start] = (buf[0][0+start] & 0xF0) + nbuf[4]
            buf[0][1+start] = nbuf[3]*16 + nbuf[2]
            buf[0][2+start] = nbuf[1]*16 + nbuf[0]

    def parse_1(self, number, buf, start, start_on_hi_nibble, numbytes):
        """Parse 5 digit number with 1 decimal"""
        self.parse_0(number*10.0, buf, start, start_on_hi_nibble, numbytes)
    
    def parse_2(self, number, buf, start, start_on_hi_nibble, numbytes):
        """Parse 5 digit number with 2 decimals"""
        self.parse_0(number*100.0, buf, start, start_on_hi_nibble, numbytes)
    
    def parse_3(self, number, buf, start, start_on_hi_nibble, numbytes):
        """Parse 5 digit number with 3 decimals"""
        self.parse_0(number*1000.0, buf, start, start_on_hi_nibble, numbytes)

    def read(self, buf):
        nbuf = [0]
        nbuf[0] = buf[0]
        self.WindspeedFormat = (nbuf[0][4] >> 4) & 0xF
        self.rain_format = (nbuf[0][4] >> 3) & 1
        self.pressure_format = (nbuf[0][4] >> 2) & 1
        self.TemperatureFormat = (nbuf[0][4] >> 1) & 1
        self.ClockMode = nbuf[0][4] & 1
        self.StormThreshold = (nbuf[0][5] >> 4) & 0xF
        self.WeatherThreshold = nbuf[0][5] & 0xF
        self.LowBatFlags = (nbuf[0][6] >> 4) & 0xF
        self.LCDContrast = nbuf[0][6] & 0xF
        self.WindDirAlarmFlags = (nbuf[0][7] << 8) | nbuf[0][8]
        self.OtherAlarmFlags = (nbuf[0][9] << 8) | nbuf[0][10]
        self.TempIndoorMax = Decode.toTemperature_5_3(nbuf, 11, 1)
        self.TempIndoorMin = Decode.toTemperature_5_3(nbuf, 13, 0)
        self.TempOutdoorMax = Decode.toTemperature_5_3(nbuf, 16, 1)
        self.TempOutdoorMin = Decode.toTemperature_5_3(nbuf, 18, 0)
        self.HumidityIndoorMax = Decode.toHumidity_2_0(nbuf, 21, 1)
        self.HumidityIndoorMin = Decode.toHumidity_2_0(nbuf, 22, 1)
        self.HumidityOutdoorMax = Decode.toHumidity_2_0(nbuf, 23, 1)
        self.HumidityOutdoorMin = Decode.toHumidity_2_0(nbuf, 24, 1)
        self.Rain24HMax = Decode.toRain_7_3(nbuf, 25, 0)
        self.HistoryInterval = nbuf[0][29]
        self.GustMax = Decode.toWindspeed_6_2(nbuf, 30)
        (self.PressureRelative_hPaMin, self.PressureRelative_inHgMin) = Decode.readPressureShared(nbuf, 33, 1)
        (self.PressureRelative_hPaMax, self.PressureRelative_inHgMax) = Decode.readPressureShared(nbuf, 38, 1)
        self.ResetMinMaxFlags = (nbuf[0][43]) << 16 | (nbuf[0][44] << 8) | (nbuf[0][45])
        self.InBufCS = (nbuf[0][46] << 8) | nbuf[0][47]
        self.OutBufCS = calc_checksum(buf, 4, end=39) + 7

        """
        Reset DewpointMax    80 00 00
        Reset DewpointMin    40 00 00 
        not used             20 00 00 
        Reset WindchillMin*  10 00 00  *dateTime only; Min is preserved
                
        Reset TempOutMax     08 00 00
        Reset TempOutMin     04 00 00
        Reset TempInMax      02 00 00
        Reset TempInMin      01 00 00 
         
        Reset Gust           00 80 00
        not used             00 40 00
        not used             00 20 00
        not used             00 10 00 
         
        Reset HumOutMax      00 08 00
        Reset HumOutMin      00 04 00 
        Reset HumInMax       00 02 00 
        Reset HumInMin       00 01 00 
          
        not used             00 00 80
        Reset Rain Total     00 00 40
        Reset last month?    00 00 20
        Reset last week?     00 00 10 
         
        Reset Rain24H        00 00 08
        Reset Rain1H         00 00 04 
        Reset PresRelMax     00 00 02 
        Reset PresRelMin     00 00 01                 
        """
        # self.ResetMinMaxFlags = 0x000000
        # logdbg('set ResetMinMaxFlags to %06x' % self.ResetMinMaxFlags)

        """
        setTemps(self,temp_format,in_temp_lo,in_temp_hi,out_temp_lo,out_temp_hi) 
        setHums(self,in_hum_lo,in_hum_hi,out_hum_lo,out_hum_hi)
        setPresRels(self,pressure_format,pres_rel_hpa_lo,pres_rel_hpa_hi,pres_rel_inhg_lo,pres_rel_inhg_hi)  
        setGust(self,wind_speed_format,gust_hi)
        setRain24H(self,rain_format,rain_24h_hi)
        """
        # Examples:
        # self.setTemps(TEMPERATURE_FORMAT_CELSIUS,1.0,41.0,2.0,42.0)
        # self.setHums(41,71,42,72)
        # self.setPresRels(PRESSURE_FORMAT_HPA,960.1,1040.1,28.36,30.72)
        # self.setGust(WINDSPEED_FORMAT_KMH,040.0)
        # self.setRain24H(RAIN_FORMAT_MM,50.0)

        # Set historyInterval to 5 minutes (default: 2 hours)
        self.HistoryInterval = HI_05MIN
        # Clear all alarm flags, otherwise the datastream from the weather
        # station will pause during an alarm and connection will be lost.
        self.WindDirAlarmFlags = 0x0000
        self.OtherAlarmFlags = 0x0000

    def testConfigChanged(self, buf):
        nbuf = [0]
        nbuf[0] = buf[0]
        nbuf[0][0] = (16 * (self.WindspeedFormat & 0xF) +
                      8 * (self.rain_format & 1) +
                      4 * (self.pressure_format & 1) +
                      2 * (self.TemperatureFormat & 1) +
                      (self.ClockMode & 1))
        nbuf[0][1] = self.WeatherThreshold & 0xF | 16 * self.StormThreshold & 0xF0
        nbuf[0][2] = self.LCDContrast & 0xF | 16 * self.LowBatFlags & 0xF0
        nbuf[0][3] = (self.OtherAlarmFlags >> 0) & 0xFF
        nbuf[0][4] = (self.OtherAlarmFlags >> 8) & 0xFF
        nbuf[0][5] = (self.WindDirAlarmFlags >> 0) & 0xFF
        nbuf[0][6] = (self.WindDirAlarmFlags >> 8) & 0xFF
        # reverse buf from here
        self.parse_2(self.PressureRelative_inHgMax, nbuf, 7, 1, 5)
        self.parse_1(self.PressureRelative_hPaMax, nbuf, 9, 0, 5)
        self.parse_2(self.PressureRelative_inHgMin, nbuf, 12, 1, 5)
        self.parse_1(self.PressureRelative_hPaMin, nbuf, 14, 0, 5)
        self.parseWind_6(self.GustMax, nbuf, 17)
        nbuf[0][20] = self.HistoryInterval & 0xF
        self.parseRain_3(self.Rain24HMax, nbuf, 21, 0, 7)
        self.parse_0(self.HumidityOutdoorMax, nbuf, 25, 1, 2)
        self.parse_0(self.HumidityOutdoorMin, nbuf, 26, 1, 2)
        self.parse_0(self.HumidityIndoorMax, nbuf, 27, 1, 2)
        self.parse_0(self.HumidityIndoorMin, nbuf, 28, 1, 2)
        self.parse_3(self.TempOutdoorMax + SensorLimits.temperature_offset, nbuf, 29, 1, 5)
        self.parse_3(self.TempOutdoorMin + SensorLimits.temperature_offset, nbuf, 31, 0, 5)
        self.parse_3(self.TempIndoorMax + SensorLimits.temperature_offset, nbuf, 34, 1, 5)
        self.parse_3(self.TempIndoorMin + SensorLimits.temperature_offset, nbuf, 36, 0, 5)
        # reverse buf to here
        Decode.reverseByteOrder(nbuf, 7, 32)
        # do not include the ResetMinMaxFlags bytes when calculating checksum
        nbuf[0][39] = (self.ResetMinMaxFlags >> 16) & 0xFF
        nbuf[0][40] = (self.ResetMinMaxFlags >> 8) & 0xFF
        nbuf[0][41] = (self.ResetMinMaxFlags >> 0) & 0xFF
        self.OutBufCS = calc_checksum(nbuf, 0, end=39) + 7
        nbuf[0][42] = (self.OutBufCS >> 8) & 0xFF
        nbuf[0][43] = (self.OutBufCS >> 0) & 0xFF
        buf[0] = nbuf[0]   
        if self.OutBufCS == self.InBufCS and self.ResetMinMaxFlags == 0:
            if DEBUG_CONFIG_DATA > 2:
                logdbg('testConfigChanged: checksum not changed: OutBufCS=%04x' % self.OutBufCS)
            changed = 0
        else:
            if DEBUG_CONFIG_DATA > 0:
                logdbg('testConfigChanged: checksum or reset_min_max_flags changed: OutBufCS=%04x InBufCS=%04x '
                       'ResetMinMaxFlags=%06x' %
                       (self.OutBufCS,
                        self.InBufCS,
                        self.ResetMinMaxFlags))
            if DEBUG_CONFIG_DATA > 1:
                self.toLog()
            changed = 1
        return changed

    def toLog(self):
        logdbg('OutBufCS=             %04x' % self.OutBufCS)
        logdbg('InBufCS=              %04x' % self.InBufCS)
        logdbg('ClockMode=            %s' % self.ClockMode)
        logdbg('TemperatureFormat=    %s' % self.TemperatureFormat)
        logdbg('pressure_format=       %s' % self.pressure_format)
        logdbg('rain_format=           %s' % self.rain_format)
        logdbg('WindspeedFormat=      %s' % self.WindspeedFormat)
        logdbg('WeatherThreshold=     %s' % self.WeatherThreshold)
        logdbg('StormThreshold=       %s' % self.StormThreshold)
        logdbg('LCDContrast=          %s' % self.LCDContrast)
        logdbg('LowBatFlags=          %01x' % self.LowBatFlags)
        logdbg('WindDirAlarmFlags=    %04x' % self.WindDirAlarmFlags)
        logdbg('OtherAlarmFlags=      %04x' % self.OtherAlarmFlags)
        logdbg('HistoryInterval=      %s' % self.HistoryInterval)
        logdbg('TempIndoorMin=       %s' % self.TempIndoorMin)
        logdbg('TempIndooMax=       %s' % self.TempIndoorMax)
        logdbg('TempOutdoorMin=      %s' % self.TempOutdoorMin)
        logdbg('TempOutdooMax=      %s' % self.TempOutdoorMax)
        logdbg('HumidityIndoorMin=   %s' % self.HumidityIndoorMin)
        logdbg('HumidityIndooMax=   %s' % self.HumidityIndoorMax)
        logdbg('HumidityOutdoorMin=  %s' % self.HumidityOutdoorMin)
        logdbg('HumidityOutdooMax=  %s' % self.HumidityOutdoorMax)
        logdbg('Rain24HMax=           %s' % self.Rain24HMax)
        logdbg('GustMax=              %s' % self.GustMax)
        logdbg('PressureRel_hPaMin=  %s' % self.PressureRelative_hPaMin)
        logdbg('PressureRel_inHgMin= %s' % self.PressureRelative_inHgMin)
        logdbg('PressureRel_hPMax=  %s' % self.PressureRelative_hPaMax)
        logdbg('PressureRel_inHMax= %s' % self.PressureRelative_inHgMax)
        logdbg('ResetMinMaxFlags=     %06x (Output only)' % self.ResetMinMaxFlags) 

    def asDict(self):
        return {
            'checksum_in': self.InBufCS,
            'checksum_out': self.OutBufCS,
            'format_clock': self.ClockMode,
            'format_temperature': self.TemperatureFormat,
            'format_pressure': self.pressure_format,
            'format_rain': self.rain_format,
            'format_windspeed': self.WindspeedFormat,
            'threshold_weather': self.WeatherThreshold,
            'threshold_storm': self.StormThreshold,
            'lcd_contrast': self.LCDContrast,
            'low_battery_flags': self.LowBatFlags,
            'alarm_flags_wind_dir': self.WindDirAlarmFlags,
            'alarm_flags_other': self.OtherAlarmFlags,
            # 'reset_minmax_flags': self.ResetMinMaxFlags,
            'history_interval': self.HistoryInterval,
            'indoor_temp_min': self.TempIndoorMin,
            'indoor_temp_max': self.TempIndoorMax,
            'indoor_humidity_min': self.HumidityIndoorMin,
            'indoor_humidity_max': self.HumidityIndoorMax,
            'outdoor_temp_min': self.TempOutdoorMin,
            'outdoor_temp_max': self.TempOutdoorMax,
            'outdoor_humidity_min': self.HumidityOutdoorMin,
            'outdoor_humidity_max': self.HumidityOutdoorMax,
            'rain_24h_max': self.Rain24HMax,
            'wind_gust_max': self.GustMax,
            'pressure_min': self.PressureRelative_hPaMin,
            'pressure_max': self.PressureRelative_hPaMax,
            # do not bother with pressure inHg
            }


class CHistoryData(object):

    def __init__(self):
        self.Time = None
        self.TempIndoor = SensorLimits.temperature_NP
        self.HumidityIndoor = SensorLimits.humidity_NP
        self.TempOutdoor = SensorLimits.temperature_NP
        self.HumidityOutdoor = SensorLimits.humidity_NP
        self.PressureRelative = None
        self.RainCounterRaw = 0
        self.WindSpeed = SensorLimits.wind_NP
        self.WindDirection = WIND_DIRECTION_NONE
        self.Gust = SensorLimits.wind_NP
        self.GustDirection = WIND_DIRECTION_NONE

    def read(self, buf):
        nbuf = [0]
        nbuf[0] = buf[0]
        self.Gust = Decode.toWindspeed_3_1(nbuf, 12, 0)
        self.GustDirection = (nbuf[0][14] >> 4) & 0xF
        self.WindSpeed = Decode.toWindspeed_3_1(nbuf, 14, 0)
        self.WindDirection = (nbuf[0][14] >> 4) & 0xF
        self.RainCounterRaw = Decode.toRain_3_1(nbuf, 16, 1)
        self.HumidityOutdoor = Decode.toHumidity_2_0(nbuf, 17, 0)
        self.HumidityIndoor = Decode.toHumidity_2_0(nbuf, 18, 0)    
        self.PressureRelative = Decode.toPressure_hPa_5_1(nbuf, 19, 0)
        self.TempIndoor = Decode.toTemperature_3_1(nbuf, 23, 0)
        self.TempOutdoor = Decode.toTemperature_3_1(nbuf, 22, 1)
        self.Time = Decode.toDateTime(nbuf, 25, 1, 'HistoryData')

    def toLog(self):
        """emit raw historical data"""
        logdbg("Time              %s" % self.Time)
        logdbg("TempIndoor=       %7.1f" % self.TempIndoor)
        logdbg("HumidityIndoor=   %7.0f" % self.HumidityIndoor)
        logdbg("TempOutdoor=      %7.1f" % self.TempOutdoor)
        logdbg("HumidityOutdoor=  %7.0f" % self.HumidityOutdoor)
        logdbg("PressureRelative= %7.1f" % self.PressureRelative)
        logdbg("RainCounterRaw=   %7.3f" % self.RainCounterRaw)
        logdbg("WindSpeed=        %7.3f" % self.WindSpeed)
        logdbg("WindDirection=    % 3s" % WeatherTraits.windDirMap[self.WindDirection])
        logdbg("Gust=             %7.3f" % self.Gust)
        logdbg("GustDirection=    % 3s" % WeatherTraits.windDirMap[self.GustDirection])

    def asDict(self):
        """emit historical data as a dict with weewx conventions"""
        return {
            'dateTime': tstr_to_ts(str(self.Time)),
            'inTemp': self.TempIndoor,
            'inHumidity': self.HumidityIndoor,
            'outTemp': self.TempOutdoor,
            'outHumidity': self.HumidityOutdoor,
            'pressure': self.PressureRelative,
            'rain': self.RainCounterRaw / 10,  # weewx wants cm
            'windSpeed': self.WindSpeed,
            'windDir': getWindDir(self.WindDirection, self.WindSpeed),
            'windGust': self.Gust,
            'windGustDir': getWindDir(self.GustDirection, self.Gust),
            }


class HistoryCache:
    def __init__(self):
        self.wait_at_start = 1
        self.clear_records()

    def clear_records(self):
        self.since_ts = 0
        self.num_rec = 0
        self.start_index = None
        self.next_index = None
        self.records = []
        self.num_outstanding_records = None
        self.num_scanned = 0
        self.last_ts = 0


class TransceiverSettings(object):
    def __init__(self):
        self.serial_number = None
        self.device_id = None


class LastStat(object):
    def __init__(self):
        self.last_battery_status = None
        self.last_link_quality = None
        self.last_history_index = None
        self.latest_history_index = None
        self.last_seen_ts = None
        self.last_weather_ts = 0
        self.last_history_ts = 0
        self.last_config_ts = 0

    def update(self, seen_ts=None, quality=None, battery=None,
               weather_ts=None, history_ts=None, config_ts=None):
        if DEBUG_COMM > 1:
            logdbg('LastStat: seen=%s quality=%s battery=%s weather=%s history=%s config=%s' %
                   (seen_ts, quality, battery, weather_ts, history_ts, config_ts))
        if seen_ts is not None:
            self.last_seen_ts = seen_ts
        if quality is not None:
            self.last_link_quality = quality
        if battery is not None:
            self.last_battery_status = battery
        if weather_ts is not None:
            self.last_weather_ts = weather_ts
        if history_ts is not None:
            self.last_history_ts = history_ts
        if config_ts is not None:
            self.last_config_ts = config_ts


class Transceiver(object):
    """USB dongle abstraction"""

    def __init__(self):
        self.devh = None
        self.timeout = 1000
        self.last_dump = None

    def open(self, vid, pid, serial):
        device = Transceiver._find_device(vid, pid, serial)
        if device is None:
            logcrt('Cannot find USB device with Vendor=0x%04x ProdID=0x%04x Serial=%s' %
                   (vid, pid, serial))
            raise weewx.WeeWxIOError('Unable to find transceiver on USB')
        self.devh = self._open_device(device)

    def close(self):
        Transceiver._close_device(self.devh)
        self.devh = None

    @staticmethod
    def _find_device(vid, pid, serial):
        for bus in usb.busses():
            for dev in bus.devices:
                if dev.idVendor == vid and dev.idProduct == pid:
                    if serial is None:
                        loginf('found transceiver at bus=%s device=%s' %
                               (bus.dirname, dev.filename))
                        return dev
                    else:
                        sn = Transceiver._read_serial(dev)
                        if str(serial) == sn:
                            loginf('found transceiver at bus=%s device=%s serial=%s' %
                                   (bus.dirname, dev.filename, sn))
                            return dev
                        else:
                            loginf('skipping transceiver with serial %s (looking for %s)' %
                                   (sn, serial))
        return None

    @staticmethod
    def _read_serial(dev):
        handle = None
        try:
            # see if we can read the serial without claiming the interface.
            # we do not want to disrupt any process that might already be
            # using the device.
            handle = dev.open()
            # other option would be to claim the interface, but this might
            # disrupt any other process that has the interface.
            handle = Transceiver._open_device(dev)
            buf = Transceiver.readCfg(handle, 0x1F9, 7)
            if buf:
                sn = ''.join(['%02d' % x for x in buf])
                return sn[0:14]
        except usb.USBError, e:
            logerr("cannot read serial number: %s" % e)
        finally:
            pass
            # if we claimed the interface, we must release it
            Transceiver._close_device(handle)
            # not sure if we have to delete the handle
            if handle is not None:
                del handle
        return None

    @staticmethod
    def _open_device(dev, interface=0):
        handle = dev.open()
        if not handle:
            raise weewx.WeeWxIOError('Open USB device failed')

        loginf('manufacturer: %s' % handle.getString(dev.iManufacturer, 30))
        loginf('product: %s' % handle.getString(dev.iProduct, 30))
        loginf('interface: %d' % interface)

        # be sure kernel does not claim the interface
        try:
            handle.detachKernelDriver(interface)
        except Exception:
            pass

        # attempt to claim the interface
        try:
            logdbg('claiming USB interface %d' % interface)
            handle.claimInterface(interface)
            handle.setAltInterface(interface)
        except usb.USBError, e:
            Transceiver._close_device(handle)
            logcrt('Unable to claim USB interface %s: %s' % (interface, e))
            raise weewx.WeeWxIOError(e)

        # FIXME: check return values
        usbWait = 0.05
        handle.getDescriptor(0x1, 0, 0x12)
        time.sleep(usbWait)
        handle.getDescriptor(0x2, 0, 0x9)
        time.sleep(usbWait)
        handle.getDescriptor(0x2, 0, 0x22)
        time.sleep(usbWait)
        handle.controlMsg(usb.TYPE_CLASS + usb.RECIP_INTERFACE,
                          0xa, [], 0x0, 0x0, 1000)
        time.sleep(usbWait)
        handle.getDescriptor(0x22, 0, 0x2a9)
        time.sleep(usbWait)
        return handle

    @staticmethod
    def _close_device(handle):
        if handle is not None:
            try:
                logdbg('releasing USB interface')
                handle.releaseInterface()
            except usb.USBError:
                pass

    def setTX(self):
        buf = [0]*0x15
        buf[0] = 0xD1
        if DEBUG_COMM > 1:
            self.dump('setTX', buf, fmt=DEBUG_DUMP_FORMAT)
        self.devh.controlMsg(usb.TYPE_CLASS + usb.RECIP_INTERFACE,
                             request=0x0000009,
                             buffer=buf,
                             value=0x00003d1,
                             index=0x0000000,
                             timeout=self.timeout)

    def setRX(self):
        buf = [0]*0x15
        buf[0] = 0xD0
        if DEBUG_COMM > 1:
            self.dump('setRX', buf, fmt=DEBUG_DUMP_FORMAT)
        self.devh.controlMsg(usb.TYPE_CLASS + usb.RECIP_INTERFACE,
                             request=0x0000009,
                             buffer=buf,
                             value=0x00003d0,
                             index=0x0000000,
                             timeout=self.timeout)

    def getState(self):
        buf = self.devh.controlMsg(requestType=usb.TYPE_CLASS |
                                   usb.RECIP_INTERFACE | usb.ENDPOINT_IN,
                                   request=usb.REQ_CLEAR_FEATURE,
                                   buffer=0x0a,
                                   value=0x00003de,
                                   index=0x0000000,
                                   timeout=self.timeout)
        if DEBUG_COMM > 1:
            self.dump('getState', buf, fmt=DEBUG_DUMP_FORMAT)
        return buf[1:3]

    def readConfigFlash(self, addr, nbytes, data):
        if nbytes > 512:
            raise Exception('bad number of bytes')
        new_data = [0] * 0x15
        while nbytes:
            buf = [0xcc] * 0x0f  # 0x15
            buf[0] = 0xdd
            buf[1] = 0x0a
            buf[2] = (addr >> 8) & 0xFF
            buf[3] = (addr >> 0) & 0xFF
            if DEBUG_COMM > 1:
                self.dump('readCfgFlash>', buf, fmt=DEBUG_DUMP_FORMAT)
            self.devh.controlMsg(usb.TYPE_CLASS + usb.RECIP_INTERFACE,
                                 request=0x0000009,
                                 buffer=buf,
                                 value=0x00003dd,
                                 index=0x0000000,
                                 timeout=self.timeout)
            buf = self.devh.controlMsg(requestType=usb.TYPE_CLASS |
                                       usb.RECIP_INTERFACE |
                                       usb.ENDPOINT_IN,
                                       request=usb.REQ_CLEAR_FEATURE,
                                       buffer=0x15,
                                       value=0x00003dc,
                                       index=0x0000000,
                                       timeout=self.timeout)
            new_data = [0] * 0x15
            if nbytes < 16:
                for i in xrange(0, nbytes):
                    new_data[i] = buf[i+4]
                nbytes = 0
            else:
                for i in xrange(0, 16):
                    new_data[i] = buf[i+4]
                nbytes -= 16
                addr += 16
            if DEBUG_COMM > 1:
                self.dump('readCfgFlash<', buf, fmt=DEBUG_DUMP_FORMAT)
        data[0] = new_data  # FIXME: new_data might be unset

    def setState(self, state):
        buf = [0]*0x15
        buf[0] = 0xd7
        buf[1] = state
        if DEBUG_COMM > 1:
            self.dump('setState', buf, fmt=DEBUG_DUMP_FORMAT)
        self.devh.controlMsg(usb.TYPE_CLASS + usb.RECIP_INTERFACE,
                             request=0x0000009,
                             buffer=buf,
                             value=0x00003d7,
                             index=0x0000000,
                             timeout=self.timeout)

    def setFrame(self, data, nbytes):
        buf = [0]*0x111
        buf[0] = 0xd5
        buf[1] = nbytes >> 8
        buf[2] = nbytes
        for i in xrange(0, nbytes):
            buf[i+3] = data[i]
        if DEBUG_COMM == 1:
            self.dump('setFrame', buf, 'short')
        elif DEBUG_COMM > 1:
            self.dump('setFrame', buf, fmt=DEBUG_DUMP_FORMAT)
        self.devh.controlMsg(usb.TYPE_CLASS + usb.RECIP_INTERFACE,
                             request=0x0000009,
                             buffer=buf,
                             value=0x00003d5,
                             index=0x0000000,
                             timeout=self.timeout)

    def getFrame(self, data, nbytes):
        buf = self.devh.controlMsg(requestType=usb.TYPE_CLASS |
                                   usb.RECIP_INTERFACE |
                                   usb.ENDPOINT_IN,
                                   request=usb.REQ_CLEAR_FEATURE,
                                   buffer=0x111,
                                   value=0x00003d6,
                                   index=0x0000000,
                                   timeout=self.timeout)
        new_data = [0] * 0x131
        new_nbytes = (buf[1] << 8 | buf[2]) & 0x1ff
        for i in xrange(0, new_nbytes):
            new_data[i] = buf[i+3]
        if DEBUG_COMM == 1:
            self.dump('getFrame', buf, 'short')
        elif DEBUG_COMM > 1:
            self.dump('getFrame', buf, fmt=DEBUG_DUMP_FORMAT)
        data[0] = new_data
        nbytes[0] = new_nbytes

    def writeReg(self, regaddr, data):
        buf = [0]*0x05
        buf[0] = 0xf0
        buf[1] = regaddr & 0x7F
        buf[2] = 0x01
        buf[3] = data
        buf[4] = 0x00
        if DEBUG_COMM > 1:
            self.dump('writeReg', buf, fmt=DEBUG_DUMP_FORMAT)
        self.devh.controlMsg(usb.TYPE_CLASS + usb.RECIP_INTERFACE,
                             request=0x0000009,
                             buffer=buf,
                             value=0x00003f0,
                             index=0x0000000,
                             timeout=self.timeout)

    def execute(self, command):
        buf = [0]*0x0f  # *0x15
        buf[0] = 0xd9
        buf[1] = command
        if DEBUG_COMM > 1:
            self.dump('execute', buf, fmt=DEBUG_DUMP_FORMAT)
        self.devh.controlMsg(usb.TYPE_CLASS + usb.RECIP_INTERFACE,
                             request=0x0000009,
                             buffer=buf,
                             value=0x00003d9,
                             index=0x0000000,
                             timeout=self.timeout)

    def setPreamblePattern(self, pattern):
        buf = [0]*0x15
        buf[0] = 0xd8
        buf[1] = pattern
        if DEBUG_COMM > 1:
            self.dump('setPreamble', buf, fmt=DEBUG_DUMP_FORMAT)
        self.devh.controlMsg(usb.TYPE_CLASS + usb.RECIP_INTERFACE,
                             request=0x0000009,
                             buffer=buf,
                             value=0x00003d8,
                             index=0x0000000,
                             timeout=self.timeout)

    # three formats, long, short, auto.  short shows only the first 16 bytes.
    # long shows the full length of the buffer.  auto shows the message length
    # as indicated by the length in the message itself for setFrame and
    # getFrame, or the first 16 bytes for any other message.
    def dump(self, cmd, buf, fmt='auto', length=16):
        strbuf = ''
        if fmt == 'auto':
            if buf[0] in [0xd5, 0x00]:
                msglen = buf[2] + 3        # use msg length for set/get frame
            else:
                msglen = 16                # otherwise do same as short format
        elif fmt == 'short':
            msglen = 16
        else:
            msglen = length                   # dedicated 'long' length
        for i, x in enumerate(buf):
            strbuf += str('%02x ' % x)
            if (i+1) % 16 == 0:
                self.dumpstr(cmd, strbuf)
                strbuf = ''
            if msglen is not None and i+1 >= msglen:
                break
        if strbuf:
            self.dumpstr(cmd, strbuf)

    # filter output that we do not care about, pad the command string.
    def dumpstr(self, cmd, strbuf):
        pad = ' ' * (15-len(cmd))
        # de15 is idle, de14 is intermediate
        if strbuf in ['de 15 00 00 00 00 ', 'de 14 00 00 00 00 ']:
            if strbuf != self.last_dump or DEBUG_COMM > 2:
                logdbg('%s: %s%s' % (cmd, pad, strbuf))
            self.last_dump = strbuf
        else:
            logdbg('%s: %s%s' % (cmd, pad, strbuf))
            self.last_dump = None

    @staticmethod
    def readCfg(handle, addr, nbytes, timeout=1000):
        new_data = [0] * 0x15
        while nbytes:
            buf = [0xcc] * 0x0f  # 0x15
            buf[0] = 0xdd
            buf[1] = 0x0a
            buf[2] = (addr >> 8) & 0xFF
            buf[3] = (addr >> 0) & 0xFF
            handle.controlMsg(usb.TYPE_CLASS + usb.RECIP_INTERFACE,
                              request=0x0000009,
                              buffer=buf,
                              value=0x00003dd,
                              index=0x0000000,
                              timeout=timeout)
            buf = handle.controlMsg(requestType=usb.TYPE_CLASS |
                                    usb.RECIP_INTERFACE | usb.ENDPOINT_IN,
                                    request=usb.REQ_CLEAR_FEATURE,
                                    buffer=0x15,
                                    value=0x00003dc,
                                    index=0x0000000,
                                    timeout=timeout)
            new_data = [0] * 0x15
            if nbytes < 16:
                for i in xrange(0, nbytes):
                    new_data[i] = buf[i+4]
                nbytes = 0
            else:
                for i in xrange(0, 16):
                    new_data[i] = buf[i+4]
                nbytes -= 16
                addr += 16
        return new_data


class AX5051RegisterNames:
    REVISION = 0x0
    SCRATCH = 0x1
    POWERMODE = 0x2
    XTALOSC = 0x3
    FIFOCTRL = 0x4
    FIFODATA = 0x5
    IRQMASK = 0x6
    IFMODE = 0x8
    PINCFG1 = 0x0C
    PINCFG2 = 0x0D
    MODULATION = 0x10
    ENCODING = 0x11
    FRAMING = 0x12
    CRCINIT3 = 0x14
    CRCINIT2 = 0x15
    CRCINIT1 = 0x16
    CRCINIT0 = 0x17
    FREQ3 = 0x20
    FREQ2 = 0x21
    FREQ1 = 0x22
    FREQ0 = 0x23
    FSKDEV2 = 0x25
    FSKDEV1 = 0x26
    FSKDEV0 = 0x27
    IFFREQHI = 0x28
    IFFREQLO = 0x29
    PLLLOOP = 0x2C
    PLLRANGING = 0x2D
    PLLRNGCLK = 0x2E
    TXPWR = 0x30
    TXRATEHI = 0x31
    TXRATEMID = 0x32
    TXRATELO = 0x33
    MODMISC = 0x34
    FIFOCONTROL2 = 0x37
    ADCMISC = 0x38
    AGCTARGET = 0x39
    AGCATTACK = 0x3A
    AGCDECAY = 0x3B
    AGCCOUNTER = 0x3C
    CICDEC = 0x3F
    DATARATEHI = 0x40
    DATARATELO = 0x41
    TMGGAINHI = 0x42
    TMGGAINLO = 0x43
    PHASEGAIN = 0x44
    FREQGAIN = 0x45
    FREQGAIN2 = 0x46
    AMPLGAIN = 0x47
    TRKFREQHI = 0x4C
    TRKFREQLO = 0x4D
    XTALCAP = 0x4F
    SPAREOUT = 0x60
    TESTOBS = 0x68
    APEOVER = 0x70
    TMMUX = 0x71
    PLLVCOI = 0x72
    PLLCPEN = 0x73
    PLLRNGMISC = 0x74
    AGCMANUAL = 0x78
    ADCDCLEVEL = 0x79
    RFMISC = 0x7A
    TXDRIVER = 0x7B
    REF = 0x7C
    RXMISC = 0x7D


class CommunicationService(object):

    def __init__(self):
        logdbg('CommunicationService.init')

        self.reg_names = dict()
        self.hid = Transceiver()
        self.transceiver_settings = TransceiverSettings()
        self.last_stat = LastStat()
        self.station_config = StationConfig()
        self.current = CurrentData()
        self.comm_mode_interval = 3
        self.transceiver_present = False
        self.registered_device_id = None

        self.firstSleep = 1
        self.nextSleep = 1
        self.pollCount = 0

        self.running = False
        self.child = None
        self.thread_wait = 60.0  # seconds

        self.command = None
        self.history_cache = HistoryCache()
        # do not set time when offset to whole hour is <= _a3_offset
        self.a3_offset = 3

    def buildFirstConfigFrame(self, buf, cs):
        logdbg('buildFirstConfigFrame: cs=%04x' % cs)
        newbuf = [0]
        newbuf[0] = [0]*9
        comInt = self.comm_mode_interval
        historyAddress = 0xFFFFFF
        newbuf[0][0] = 0xf0
        newbuf[0][1] = 0xf0
        newbuf[0][2] = ACTION_GET_CONFIG
        newbuf[0][3] = (cs >> 8) & 0xff
        newbuf[0][4] = (cs >> 0) & 0xff
        newbuf[0][5] = (comInt >> 4) & 0xff
        newbuf[0][6] = (historyAddress >> 16) & 0x0f | 16 * (comInt & 0xf)
        newbuf[0][7] = (historyAddress >> 8) & 0xff
        newbuf[0][8] = historyAddress & 0xff
        buf[0] = newbuf[0]
        length = 0x09
        return length

    def buildConfigFrame(self, buf):
        logdbg("buildConfigFrame")
        newbuf = [0]
        newbuf[0] = [0]*48
        cfgbuf = [0]
        cfgbuf[0] = [0]*44
        changed = self.station_config.testConfigChanged(cfgbuf)
        self.hid.dump('OutBuf', cfgbuf[0], fmt='long', length=48)
        if changed:
            self.hid.dump('OutBuf', cfgbuf[0], fmt='long', length=48)
            newbuf[0][0] = buf[0][0]
            newbuf[0][1] = buf[0][1]
            newbuf[0][2] = ACTION_SEND_CONFIG  # 0x40 # change this value if we won't store config
            newbuf[0][3] = buf[0][3]
            for i in xrange(0, 44):
                newbuf[0][i+4] = cfgbuf[0][i]
            buf[0] = newbuf[0]
            length = 48  # 0x30
        else:  # current config not up to date; do not write yet
            length = 0
        return length

    @staticmethod
    def buildTimeFrame(buf, cs):
        logdbg("buildTimeFrame: cs=%04x" % cs)

        now = time.time()
        tm = time.localtime(now)

        newbuf = [0]
        newbuf[0] = buf[0]
        # 00000000: d5 00 0c 00 32 c0 00 8f 45 25 15 91 31 20 01 00
        # 00000000: d5 00 0c 00 32 c0 06 c1 47 25 15 91 31 20 01 00
        #                             3  4  5  6  7  8  9 10 11
        newbuf[0][2] = ACTION_SEND_TIME  # 0xc0
        newbuf[0][3] = (cs >> 8) & 0xFF
        newbuf[0][4] = (cs >> 0) & 0xFF
        newbuf[0][5] = (tm[5] % 10) + 0x10 * (tm[5] // 10)  # sec
        newbuf[0][6] = (tm[4] % 10) + 0x10 * (tm[4] // 10)  # min
        newbuf[0][7] = (tm[3] % 10) + 0x10 * (tm[3] // 10)  # hour
        # DayOfWeek = tm[6] - 1; #ole from 1 - 7 - 1=Sun... 0-6 0=Sun
        DayOfWeek = tm[6]       # py  from 0 - 6 - 0=Mon
        newbuf[0][8] = DayOfWeek % 10 + 0x10 * (tm[2] % 10)          # DoW + Day
        newbuf[0][9] = (tm[2] // 10) + 0x10 * (tm[1] % 10)          # day + month
        newbuf[0][10] = (tm[1] // 10) + 0x10 * ((tm[0] - 2000) % 10)  # month + year
        newbuf[0][11] = (tm[0] - 2000) // 10                          # year
        buf[0] = newbuf[0]
        length = 0x0c
        return length

    def buildACKFrame(self, buf, action, cs, hidx=None):
        if DEBUG_COMM > 1:
            logdbg("buildACKFrame: action=%x cs=%04x historyIndex=%s" %
                   (action, cs, hidx))
        newbuf = [0]
        newbuf[0] = [0]*9
        for i in xrange(0, 2):
            newbuf[0][i] = buf[0][i]

        comInt = self.comm_mode_interval

        # When last weather is stale, change action to get current weather
        # This is only needed during long periods of history data catchup
        if self.command == ACTION_GET_HISTORY:
            now = int(time.time())
            age = now - self.last_stat.last_weather_ts
            # Morphing action only with GetHistory requests, 
            # and stale data after a period of twice the CommModeInterval,
            # but not with init GetHistory requests (0xF0)
            if action == ACTION_GET_HISTORY and age >= (comInt + 1) * 2 and newbuf[0][1] != 0xF0:
                if DEBUG_COMM > 0:
                    logdbg('buildACKFrame: morphing action from %d to 5 (age=%s)' % (action, age))
                action = ACTION_GET_CURRENT

        if hidx is None:
            if self.last_stat.latest_history_index is not None:
                hidx = self.last_stat.latest_history_index
        if hidx is None or hidx < 0 or hidx >= WS28xxDriver.max_records:
            haddr = 0xffffff
        else:
            haddr = index_to_addr(hidx)
        if DEBUG_COMM > 1:
            logdbg('buildACKFrame: idx: %s addr: 0x%04x' % (hidx, haddr))

        newbuf[0][2] = action & 0xF
        newbuf[0][3] = (cs >> 8) & 0xFF
        newbuf[0][4] = (cs >> 0) & 0xFF
        newbuf[0][5] = (comInt >> 4) & 0xFF
        newbuf[0][6] = (haddr >> 16) & 0x0F | 16 * (comInt & 0xF)
        newbuf[0][7] = (haddr >> 8) & 0xFF
        newbuf[0][8] = haddr & 0xFF

        # d5 00 09 f0 f0 03 00 32 00 3f ff ff
        buf[0] = newbuf[0]
        return 9

    def handleWsAck(self, buf):
        logdbg('handleWsAck')
        self.last_stat.update(seen_ts=int(time.time()),
                              quality=(buf[0][3] & 0x7f),
                              battery=(buf[0][2] & 0xf))

    def handleConfig(self, buf, length):
        logdbg('handleConfig: %s' % self.timing())
        if DEBUG_CONFIG_DATA > 1:
            self.hid.dump('InBuf', buf[0], fmt='long', length=48)
        newbuf = [0]
        newbuf[0] = buf[0]
        newlength = [0]
        now = int(time.time())
        self.station_config.read(newbuf)
        if DEBUG_CONFIG_DATA > 1:
            self.station_config.toLog()
        self.last_stat.update(seen_ts=now,
                              quality=(buf[0][3] & 0x7f),
                              battery=(buf[0][2] & 0xf),
                              config_ts=now)
        cs = newbuf[0][47] | (newbuf[0][46] << 8)
        self.setSleep(0.300, 0.010)
        newlength[0] = self.buildACKFrame(newbuf, ACTION_GET_HISTORY, cs)

        buf[0] = newbuf[0]
        length[0] = newlength[0]

    def handleCurrentData(self, buf, length):
        if DEBUG_WEATHER_DATA > 0:
            logdbg('handleCurrentData: %s' % self.timing())

        now = int(time.time())

        # update the weather data cache if changed or stale
        age = now - self.last_stat.last_weather_ts
        if age >= self.comm_mode_interval:
            data = CurrentData()
            data.read(buf)
            self.current = data
            if DEBUG_WEATHER_DATA > 1:
                data.toLog()
        else:
            if DEBUG_WEATHER_DATA > 1:
                logdbg('new weather data within %s received; skip data; ts=%s' % (age, now))

        # update the connection cache
        self.last_stat.update(seen_ts=now,
                              quality=(buf[0][3] & 0x7f),
                              battery=(buf[0][2] & 0xf),
                              weather_ts=now)

        newbuf = [0]
        newbuf[0] = buf[0]
        newlength = [0]

        cs = newbuf[0][5] | (newbuf[0][4] << 8)

        cfgbuf = [0]
        cfgbuf[0] = [0]*44
        changed = self.station_config.testConfigChanged(cfgbuf)
        inBufCS = self.station_config.getInBufCS()
        if inBufCS == 0 or inBufCS != cs:
            # request for a get config
            logdbg('handleCurrentData: inBufCS of station does not match')
            self.setSleep(0.300, 0.010)
            newlength[0] = self.buildACKFrame(newbuf, ACTION_GET_CONFIG, cs)
        elif changed:
            # Request for a set config
            logdbg('handleCurrentData: outBufCS of station changed')
            self.setSleep(0.300, 0.010)
            newlength[0] = self.buildACKFrame(newbuf, ACTION_REQ_SET_CONFIG, cs)
        else:
            # Request for either a history message or a current weather message
            # In general we don't use ACTION_GET_CURRENT to ask for a current
            # weather  message; they also come when requested for
            # ACTION_GET_HISTORY. This we learned from the Heavy Weather Pro
            # messages (via USB sniffer).
            self.setSleep(0.300, 0.010)
            newlength[0] = self.buildACKFrame(newbuf, ACTION_GET_HISTORY, cs)

        length[0] = newlength[0]
        buf[0] = newbuf[0]

    def handleHistoryData(self, buf, length):
        if DEBUG_HISTORY_DATA > 0:
            logdbg('handleHistoryData: %s' % self.timing())

        now = int(time.time())
        self.last_stat.update(seen_ts=now,
                              quality=(buf[0][3] & 0x7f),
                              battery=(buf[0][2] & 0xf),
                              history_ts=now)

        newbuf = [0]
        newbuf[0] = buf[0]
        newlength = [0]
        data = CHistoryData()
        data.read(newbuf)
        if DEBUG_HISTORY_DATA > 1:
            data.toLog()

        cs = newbuf[0][5] | (newbuf[0][4] << 8)
        latestAddr = bytes_to_addr(buf[0][6], buf[0][7], buf[0][8])
        thisAddr = bytes_to_addr(buf[0][9], buf[0][10], buf[0][11])
        latestIndex = addr_to_index(latestAddr)
        thisIndex = addr_to_index(thisAddr)
        ts = tstr_to_ts(str(data.Time))

        nrec = get_index(latestIndex - thisIndex)
        logdbg('handleHistoryData: time=%s'
               ' this=%d (0x%04x) latest=%d (0x%04x) nrec=%d' %
               (data.Time, thisIndex, thisAddr, latestIndex, latestAddr, nrec))

        # track the latest history index
        self.last_stat.last_history_index = thisIndex
        self.last_stat.latest_history_index = latestIndex

        nextIndex = None
        if self.command == ACTION_GET_HISTORY:
            if self.history_cache.start_index is None:
                if self.history_cache.num_rec > 0:
                    loginf('handleHistoryData: request for %s records' %
                           self.history_cache.num_rec)
                    nreq = self.history_cache.num_rec
                else:
                    loginf('handleHistoryData: request records since %s' %
                           weeutil.weeutil.timestamp_to_string(self.history_cache.since_ts))
                    span = int(time.time()) - self.history_cache.since_ts
                    # FIXME: what if we do not have config data yet?
                    cfg = self.getConfigData().asDict()
                    arcint = 60 * history_intervals.get(cfg['history_interval'])
                    # FIXME: this assumes a constant archive interval for all
                    # records in the station history
                    nreq = int(span / arcint) + 5  # FIXME: punt 5
                if nreq > nrec:
                    loginf('handleHistoryData: too many records requested (%d)'
                           ', clipping to number stored (%d)' % (nreq, nrec))
                    nreq = nrec
                idx = get_index(latestIndex - nreq)
                self.history_cache.start_index = idx
                self.history_cache.next_index = idx
                self.last_stat.last_history_index = idx
                self.history_cache.num_outstanding_records = nreq
                logdbg('handleHistoryData: start_index=%s'
                       ' num_outstanding_records=%s' % (idx, nreq))
                nextIndex = idx
            elif self.history_cache.next_index is not None:
                # thisIndex should be the next record after next_index
                thisIndexTst = get_next_index(self.history_cache.next_index)
                if thisIndexTst == thisIndex:
                    self.history_cache.num_scanned += 1
                    # get the next history record
                    if ts is not None and self.history_cache.since_ts <= ts:
                        # Check if two records in a row with the same ts
                        if self.history_cache.last_ts == ts:
                            logdbg('handleHistoryData: remove previous record'
                                   ' with duplicate timestamp: %s' %
                                   weeutil.weeutil.timestamp_to_string(ts))
                            self.history_cache.records.pop()
                        self.history_cache.last_ts = ts
                        # append to the history
                        logdbg('handleHistoryData: appending history record'
                               ' %s: %s' % (thisIndex, data.asDict()))
                        self.history_cache.records.append(data.asDict())
                        self.history_cache.num_outstanding_records = nrec
                    elif ts is None:
                        logerr('handleHistoryData: skip record: this_ts=None')
                    else:
                        logdbg('handleHistoryData: skip record: since_ts=%s this_ts=%s' %
                               (weeutil.weeutil.timestamp_to_string(self.history_cache.since_ts),
                                weeutil.weeutil.timestamp_to_string(ts)))
                    self.history_cache.next_index = thisIndex
                else:
                    loginf('handleHistoryData: index mismatch: %s != %s' %
                           (thisIndexTst, thisIndex))
                nextIndex = self.history_cache.next_index

        logdbg('handleHistoryData: next=%s' % nextIndex)
        self.setSleep(0.300, 0.010)
        newlength[0] = self.buildACKFrame(newbuf, ACTION_GET_HISTORY, cs, nextIndex)

        length[0] = newlength[0]
        buf[0] = newbuf[0]

    def handleNextAction(self, buf, length):
        newbuf = [0]
        newbuf[0] = buf[0]
        newlength = [0]
        newlength[0] = length[0]
        self.last_stat.update(seen_ts=int(time.time()),
                              quality=(buf[0][3] & 0x7f))
        cs = newbuf[0][5] | (newbuf[0][4] << 8)
        if (buf[0][2] & 0xEF) == RESPONSE_REQ_FIRST_CONFIG:
            logdbg('handleNextAction: a1 (first-time config)')
            self.setSleep(0.085, 0.005)
            newlength[0] = self.buildFirstConfigFrame(newbuf, cs)
        elif (buf[0][2] & 0xEF) == RESPONSE_REQ_SET_CONFIG:
            logdbg('handleNextAction: a2 (set config data)')
            self.setSleep(0.085, 0.005)
            newlength[0] = self.buildConfigFrame(newbuf)
        elif (buf[0][2] & 0xEF) == RESPONSE_REQ_SET_TIME:
            logdbg('handleNextAction: a3 (set time data)')
            now = int(time.time())
            age = now - self.last_stat.last_weather_ts
            if age >= (self.comm_mode_interval + 1) * 2:
                # always set time if init or stale communication
                self.setSleep(0.085, 0.005)
                newlength[0] = self.buildTimeFrame(newbuf, cs)
            else:
                # When time is set at the whole hour we may get an extra
                # historical record with time stamp a history period ahead
                # We will skip settime if offset to whole hour is too small
                # (time difference between WS and server < self.a3_offset)
                m, s = divmod(now, 60)
                h, m = divmod(m, 60)
                logdbg('Time: hh:%02d:%02d' % (m, s))
                if (m == 59 and s >= (60 - self.a3_offset)) or (m == 0 and s <= self.a3_offset):
                    logdbg('Skip settime; time difference <= %s s' % int(self.a3_offset))
                    self.setSleep(0.300, 0.010)
                    newlength[0] = self.buildACKFrame(newbuf, ACTION_GET_HISTORY, cs)
                else:
                    # set time
                    self.setSleep(0.085, 0.005)
                    newlength[0] = self.buildTimeFrame(newbuf, cs)
        else:
            logdbg('handleNextAction: %02x' % (buf[0][2] & 0xEF))
            self.setSleep(0.300, 0.010)
            newlength[0] = self.buildACKFrame(newbuf, ACTION_GET_HISTORY, cs)

        length[0] = newlength[0]
        buf[0] = newbuf[0]

    def generateResponse(self, buf, length):
        if DEBUG_COMM > 1:
            logdbg('generateResponse: %s' % self.timing())
        newbuf = [0]
        newbuf[0] = buf[0]
        newlength = [0]
        newlength[0] = length[0]
        if length[0] == 0:
            raise BadResponse('zero length buf')

        bufID = (buf[0][0] << 8) | buf[0][1]
        respType = (buf[0][2] & 0xE0)
        if DEBUG_COMM > 1:
            logdbg("generateResponse: id=%04x resp=%x length=%x" %
                   (bufID, respType, length[0]))
        deviceID = self.getDeviceID()
        if bufID != 0xF0F0:
            self.set_registered_device_id(bufID)

        if bufID == 0xF0F0:
            loginf('generateResponse: console not paired, attempting to pair to 0x%04x' % deviceID)
            newlength[0] = self.buildACKFrame(newbuf, ACTION_GET_CONFIG, deviceID, 0xFFFF)
        elif bufID == deviceID:
            if respType == RESPONSE_DATA_WRITTEN:
                #    00000000: 00 00 06 00 32 20
                if length[0] == 0x06:
                    self.station_config.setResetMinMaxFlags(0)
                    self.hid.setRX()
                    raise DataWritten()
                else:
                    raise BadResponse('len=%x resp=%x' % (length[0], respType))
            elif respType == RESPONSE_GET_CONFIG:
                #    00000000: 00 00 30 00 32 40
                if length[0] == 0x30:
                    self.handleConfig(newbuf, newlength)
                else:
                    raise BadResponse('len=%x resp=%x' % (length[0], respType))
            elif respType == RESPONSE_GET_CURRENT:
                #    00000000: 00 00 d7 00 32 60
                if length[0] == 0xd7:  # 215
                    self.handleCurrentData(newbuf, newlength)
                else:
                    raise BadResponse('len=%x resp=%x' % (length[0], respType))
            elif respType == RESPONSE_GET_HISTORY:
                #    00000000: 00 00 1e 00 32 80
                if length[0] == 0x1e:
                    self.handleHistoryData(newbuf, newlength)
                else:
                    raise BadResponse('len=%x resp=%x' % (length[0], respType))
            elif respType == RESPONSE_REQUEST:
                #    00000000: 00 00 06 f0 f0 a1
                #    00000000: 00 00 06 00 32 a3
                #    00000000: 00 00 06 00 32 a2
                if length[0] == 0x06:
                    self.handleNextAction(newbuf, newlength)
                else:
                    raise BadResponse('len=%x resp=%x' % (length[0], respType))
            else:
                raise BadResponse('unexpected response type %x' % respType)
        elif respType not in [0x20, 0x40, 0x60, 0x80, 0xa1, 0xa2, 0xa3]:
            # message is probably corrupt
            raise BadResponse('unknown response type %x' % respType)
        else:
            msg = 'message from console contains unknown device ID (id=%04x resp=%x)' % (bufID, respType)
            logdbg(msg)
            log_frame(length[0], buf[0])
            raise BadResponse(msg)

        buf[0] = newbuf[0]
        length[0] = newlength[0]

    def configureRegisterNames(self):
        self.reg_names[AX5051RegisterNames.IFMODE] = 0x00
        self.reg_names[AX5051RegisterNames.MODULATION] = 0x41  # fsk
        self.reg_names[AX5051RegisterNames.ENCODING] = 0x07
        self.reg_names[AX5051RegisterNames.FRAMING] = 0x84  # 1000:0100 ##?hdlc? |1000 010 0
        self.reg_names[AX5051RegisterNames.CRCINIT3] = 0xff
        self.reg_names[AX5051RegisterNames.CRCINIT2] = 0xff
        self.reg_names[AX5051RegisterNames.CRCINIT1] = 0xff
        self.reg_names[AX5051RegisterNames.CRCINIT0] = 0xff
        self.reg_names[AX5051RegisterNames.FREQ3] = 0x38
        self.reg_names[AX5051RegisterNames.FREQ2] = 0x90
        self.reg_names[AX5051RegisterNames.FREQ1] = 0x00
        self.reg_names[AX5051RegisterNames.FREQ0] = 0x01
        self.reg_names[AX5051RegisterNames.PLLLOOP] = 0x1d
        self.reg_names[AX5051RegisterNames.PLLRANGING] = 0x08
        self.reg_names[AX5051RegisterNames.PLLRNGCLK] = 0x03
        self.reg_names[AX5051RegisterNames.MODMISC] = 0x03
        self.reg_names[AX5051RegisterNames.SPAREOUT] = 0x00
        self.reg_names[AX5051RegisterNames.TESTOBS] = 0x00
        self.reg_names[AX5051RegisterNames.APEOVER] = 0x00
        self.reg_names[AX5051RegisterNames.TMMUX] = 0x00
        self.reg_names[AX5051RegisterNames.PLLVCOI] = 0x01
        self.reg_names[AX5051RegisterNames.PLLCPEN] = 0x01
        self.reg_names[AX5051RegisterNames.RFMISC] = 0xb0
        self.reg_names[AX5051RegisterNames.REF] = 0x23
        self.reg_names[AX5051RegisterNames.IFFREQHI] = 0x20
        self.reg_names[AX5051RegisterNames.IFFREQLO] = 0x00
        self.reg_names[AX5051RegisterNames.ADCMISC] = 0x01
        self.reg_names[AX5051RegisterNames.AGCTARGET] = 0x0e
        self.reg_names[AX5051RegisterNames.AGCATTACK] = 0x11
        self.reg_names[AX5051RegisterNames.AGCDECAY] = 0x0e
        self.reg_names[AX5051RegisterNames.CICDEC] = 0x3f
        self.reg_names[AX5051RegisterNames.DATARATEHI] = 0x19
        self.reg_names[AX5051RegisterNames.DATARATELO] = 0x66
        self.reg_names[AX5051RegisterNames.TMGGAINHI] = 0x01
        self.reg_names[AX5051RegisterNames.TMGGAINLO] = 0x96
        self.reg_names[AX5051RegisterNames.PHASEGAIN] = 0x03
        self.reg_names[AX5051RegisterNames.FREQGAIN] = 0x04
        self.reg_names[AX5051RegisterNames.FREQGAIN2] = 0x0a
        self.reg_names[AX5051RegisterNames.AMPLGAIN] = 0x06
        self.reg_names[AX5051RegisterNames.AGCMANUAL] = 0x00
        self.reg_names[AX5051RegisterNames.ADCDCLEVEL] = 0x10
        self.reg_names[AX5051RegisterNames.RXMISC] = 0x35
        self.reg_names[AX5051RegisterNames.FSKDEV2] = 0x00
        self.reg_names[AX5051RegisterNames.FSKDEV1] = 0x31
        self.reg_names[AX5051RegisterNames.FSKDEV0] = 0x27
        self.reg_names[AX5051RegisterNames.TXPWR] = 0x03
        self.reg_names[AX5051RegisterNames.TXRATEHI] = 0x00
        self.reg_names[AX5051RegisterNames.TXRATEMID] = 0x51
        self.reg_names[AX5051RegisterNames.TXRATELO] = 0xec
        self.reg_names[AX5051RegisterNames.TXDRIVER] = 0x88

    def initTransceiver(self, frequency_standard):
        self.configureRegisterNames()

        # calculate the frequency then set frequency registers
        logdbg('frequency standard: %s' % frequency_standard)
        freq = frequencies.get(frequency_standard, frequencies['EU'])
        loginf('base frequency: %d' % freq)
        freqVal = long(freq / 16000000.0 * 16777216.0)
        corVec = [None]
        self.hid.readConfigFlash(0x1F5, 4, corVec)
        corVal = corVec[0][0] << 8
        corVal |= corVec[0][1]
        corVal <<= 8
        corVal |= corVec[0][2]
        corVal <<= 8
        corVal |= corVec[0][3]
        loginf('frequency correction: %d (0x%x)' % (corVal, corVal))
        freqVal += corVal
        if not (freqVal % 2):
            freqVal += 1
        loginf('adjusted frequency: %d (0x%x)' % (freqVal, freqVal))
        self.reg_names[AX5051RegisterNames.FREQ3] = (freqVal >> 24) & 0xFF
        self.reg_names[AX5051RegisterNames.FREQ2] = (freqVal >> 16) & 0xFF
        self.reg_names[AX5051RegisterNames.FREQ1] = (freqVal >> 8) & 0xFF
        self.reg_names[AX5051RegisterNames.FREQ0] = freqVal & 0xFF
        logdbg('frequency registers: %x %x %x %x' % (
            self.reg_names[AX5051RegisterNames.FREQ3],
            self.reg_names[AX5051RegisterNames.FREQ2],
            self.reg_names[AX5051RegisterNames.FREQ1],
            self.reg_names[AX5051RegisterNames.FREQ0]))

        # figure out the transceiver id
        buf = [None]
        self.hid.readConfigFlash(0x1F9, 7, buf)
        tid = buf[0][5] << 8
        tid += buf[0][6]
        loginf('transceiver identifier: %d (0x%04x)' % (tid, tid))
        self.transceiver_settings.device_id = tid

        # figure out the transceiver serial number
        sn = ''.join(['%02d' % x for x in buf[0][0:7]])
        loginf('transceiver serial: %s' % sn)
        self.transceiver_settings.serial_number = sn

        for r in self.reg_names:
            self.hid.writeReg(r, self.reg_names[r])

    def setup(self, frequency_standard, comm_interval,
              vendor_id, product_id, serial):
        loginf("comm_interval is %s" % comm_interval)
        self.comm_mode_interval = comm_interval
        self.hid.open(vendor_id, product_id, serial)
        self.initTransceiver(frequency_standard)
        self.transceiver_present = True

    def teardown(self):
        self.hid.close()

    def getTransceiverPresent(self):
        return self.transceiver_present

    def set_registered_device_id(self, val):
        if val != self.registered_device_id:
            loginf("console is paired to device with ID %04x" % val)
        self.registered_device_id = val

    def getDeviceRegistered(self):
        if (self.registered_device_id is None
            or self.transceiver_settings.device_id is None
            or self.registered_device_id != self.transceiver_settings.device_id):
            return False
        return True

    def getDeviceID(self):
        return self.transceiver_settings.device_id

    def getTransceiverSerNo(self):
        return self.transceiver_settings.serial_number

    # FIXME: make this thread-safe
    def getCurrentData(self):
        return self.current

    # FIXME: make this thread-safe
    def getLastStat(self):
        return self.last_stat

    # FIXME: make this thread-safe
    def getConfigData(self):
        return self.station_config

    def startCachingHistory(self, since_ts=0, num_rec=0):
        self.history_cache.clear_records()
        if since_ts is None:
            since_ts = 0
        self.history_cache.since_ts = since_ts
        if num_rec > WS28xxDriver.max_records - 2:
            num_rec = WS28xxDriver.max_records - 2
        self.history_cache.num_rec = num_rec
        self.command = ACTION_GET_HISTORY

    def stopCachingHistory(self):
        self.command = None

    def getUncachedHistoryCount(self):
        return self.history_cache.num_outstanding_records

    def getNextHistoryIndex(self):
        return self.history_cache.next_index

    def getNumHistoryScanned(self):
        return self.history_cache.num_scanned

    def getLatestHistoryIndex(self):
        return self.last_stat.latest_history_index

    def getHistoryCacheRecords(self):
        return self.history_cache.records

    def clearHistoryCache(self):
        self.history_cache.clear_records()

    def clearWaitAtStart(self):
        self.history_cache.wait_at_start = 0

    def startRFThread(self):
        if self.child is not None:
            return
        logdbg('startRFThread: spawning RF thread')
        self.running = True
        self.child = threading.Thread(target=self.doRF)
        self.child.setName('RFComm')
        self.child.setDaemon(True)
        self.child.start()

    def stopRFThread(self):
        self.running = False
        logdbg('stopRFThread: waiting for RF thread to terminate')
        self.child.join(self.thread_wait)
        if self.child.isAlive():
            logerr('unable to terminate RF thread after %d seconds' %
                   self.thread_wait)
        else:
            self.child = None

    def isRunning(self):
        return self.running

    def doRF(self):
        try:
            logdbg('setting up rf communication')
            self.doRFSetup()
            # wait for genStartupRecords to start
            while self.history_cache.wait_at_start == 1:
                time.sleep(1)
            logdbg('starting rf communication')
            while self.running:
                self.doRFCommunication()
        except Exception, e:
            logerr('exception in doRF: %s' % e)
            if weewx.debug:
                log_traceback(dst=syslog.LOG_DEBUG)
            self.running = False
            raise
        finally:
            logdbg('stopping rf communication')

    # it is probably not necessary to have two setPreamblePattern invocations.
    # however, HeavyWeatherPro seems to do it this way on a first time config.
    # doing it this way makes configuration easier during a factory reset and
    # when re-establishing communication with the station sensors.
    def doRFSetup(self):
        self.hid.execute(5)
        self.hid.setPreamblePattern(0xaa)
        self.hid.setState(0)
        time.sleep(1)
        self.hid.setRX()

        self.hid.setPreamblePattern(0xaa)
        self.hid.setState(0x1e)
        time.sleep(1)
        self.hid.setRX()
        self.setSleep(0.085, 0.005)

    def doRFCommunication(self):
        time.sleep(self.firstSleep)
        self.pollCount = 0
        while self.running:
            statebuf = [0] * 2
            try:
                statebuf = self.hid.getState()
            except Exception, e:
                logerr('getState failed: %s' % e)
                time.sleep(5)
                pass
            self.pollCount += 1
            if statebuf[0] == 0x16:
                break
            time.sleep(self.nextSleep)
        else:
            return

        datalength = [0]
        datalength[0] = 0
        framebuf = [0]
        framebuf[0] = [0]*0x03
        self.hid.getFrame(framebuf, datalength)
        try:
            self.generateResponse(framebuf, datalength)
            self.hid.setFrame(framebuf[0], datalength[0])
        except BadResponse, e:
            logerr('generateResponse failed: %s' % e)
        except DataWritten:
            logdbg('SetTime/SetConfig data written')
        self.hid.setTX()

    # these are for diagnostics and debugging
    def setSleep(self, firstsleep, nextsleep):
        self.firstSleep = firstsleep
        self.nextSleep = nextsleep

    def timing(self):
        s = self.firstSleep + self.nextSleep * (self.pollCount - 1)
        return 'sleep=%s first=%s next=%s count=%s' % (
            s, self.firstSleep, self.nextSleep, self.pollCount)

