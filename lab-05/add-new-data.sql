create table if not exists json_import(
    id serial primary key,
    file_name text not null,
    data jsonb not null
);

alter table car add column if not exists specs jsonb;
alter table race_entry add column if not exists ;

insert into json_import (file_name, data) values ('car_specs.json', pg_read_file('/workspace/data/car_specs.json')::jsonb);
update car c
set specs = cs.specs
from jsonb_to_recordset((select data from json_import where file_name = 'car_specs.json' order by id desc limit 1))
    cs(car_id int, specs jsonb)
where c.car_id = cs.car_id;
