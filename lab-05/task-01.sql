-- -- Одна строка это json
-- select to_jsonb(t) from track t;

-- -- Только выбранные значения
-- select jsonb_build_object(
--     'id', d.driver_id,
--     'name', d.full_name,
--     'born', d.birth_city || ' ' || d.birth_date,
--     'license', d.license_class,
--     'country', d.country
-- )
-- from driver d;

-- -- best_lap в качетсве интервала и best_lap_s в качестве числа
-- select jsonb_build_object(
--     'driver_id', re.driver_id,
--     'date', re.race_date,
--     'best_lap', re.best_lap,
--     'best_lap_s', extract(epoch from re.best_lap)
-- )
-- from race_entry re
-- where best_lap is not null;

-- -- Все треки один массивом
-- select jsonb_pretty(jsonb_agg(t order by t.track_id))
-- from track t;

-- 

-- -- пилот + гонки за период контаркта
-- select jsonb_build_object(
--     'id', d.driver_id,
--     'races_date', ARRAY(
--         select race_date
--         from race_entry re
--         where re.driver_id = d.driver_id and re.race_date between c.start_date and c.end_date
--     )
-- )
-- from driver d
-- join contract c using (driver_id)

-- -- Результаты гонок
-- select jsonb_pretty(jsonb_agg(jsonb_build_object(
--     'track', t.name,
--     'date', re.race_date,
--     'results', (
--         select jsonb_agg(jsonb_build_object(
--             'driver_id', re1.driver_id,
--             'status', re1.status,
--             'position', re1.finish_position,
--             'time', re1.total_time
--         ) order by re1.finish_position nulls last, re1.driver_id)
--         from race_entry re1
--         where re1.race_date = re.race_date and re1.track_id = re.track_id
--     )
-- )))
-- from race_entry re
-- join track t using (track_id)
-- where re.race_date >= '2024-01-01'
-- group by re.race_date, re.track_id, t.name
-- order by re.race_date desc;

