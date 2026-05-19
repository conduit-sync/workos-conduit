Bronze
watermark-<timestamp>.json --> Status --> InProgress --> S3
 

Silver



Gold
After all stages:
Update watermark-<timestamp>.json --> successful --> S3 -- using latest timestamp
Move the file to watermark.json

Customer --> Hashing, no of is 300 or 400


Hashing --> Needed only if there are multiple identifiers and they are changing + getting external systems
Watermarking
 --> Every pipeline, DateDimension --> Given Date example: 20260429 Q2 H1 WorkingDay year month day tues US-Holiday business-Day
 --> T+7 days

Merging


20260429 Q2 H1 WorkingDay year month day tues US-HolidayT business-DayT - d98df118fcb8ecdf727e57a22d172e9acdb9685c8c5ce590b7cecf585425f45a
d98df118fcb8ecdf727e57a22d172e9acdb9685c8c5ce590b7cecf585425f45a

20260429 Q2 H1 WorkingDay year month day tues US-HolidayF business-DayT - 382ccf59769f1386fd408283d1140b12a170fc45c3a144bf7c47897801a69326




