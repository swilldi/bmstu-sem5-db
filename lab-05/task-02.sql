create table if not exists track_copy (like track including all);
insert into track_copy
select * from jsonb_populate_recordset(null::track, (select data from json_import where file_name = 'track.json' order by id desc limit 1));

(select * from track except select * from track_copy)
union all
(select * from track_copy except select * from track);

drop table track_copy