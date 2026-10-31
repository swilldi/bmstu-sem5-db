begin;

alter table race_entry add column if not exists pit_stops jsonb;

update race_entry re
set pit_stops = ps.pit_stops
from jsonb_to_recordset(pg_read_file('/workspace/data/pit_stops.json')::jsonb) as ps(driver_id int, race_date date, pit_stops jsonb)
where re.driver_id = ps.driver_id and re.race_date = ps.race_date;

-- ручками добавим новое
/*
driver_id | race_date  
-----------+------------
        8 | 1950-05-13 |
       10 | 1950-05-13 |
*/

update race_entry
set pit_stops = '[ 
    { "lap": 4, "duration_s": 13.5, "tyre": "soft" },
    { "lap": 10, "duration_s": 4, "tyre": "hard"}
]'
where driver_id = 8 and race_date = '1950-05-13';

update race_entry
set pit_stops = '[ 
    { "lap": 8, "duration_s": 30.9, "tyre": "medium" }
]'
where driver_id = 10 and race_date = '1950-05-13';

rollback;
