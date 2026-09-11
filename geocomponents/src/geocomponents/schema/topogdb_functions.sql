-- bespoke functions

create schema if not exists topogdb;


-- footprint_facts holds the footprint of a geometry and a set of booleans
-- to help validation
do $$
begin
    if not exists (
        select 1
        from pg_type t
        join pg_namespace n on n.oid = t.typnamespace
        where n.nspname = 'topogdb'
          and t.typname = 'footprint_facts'
    ) then
        -- Changing this composite type later needs a manual
        -- drop type topogdb.footprint_facts cascade before reapplying.
        create type topogdb.footprint_facts as (
            footprint       geometry,
            areas           integer,
            holes           integer,
            curves_all_used boolean
        );
    end if;
end;
$$;

comment on type topogdb.footprint_facts is
    'Set of facts to validate a footprint. See individual descriptions.';

comment on column topogdb.footprint_facts.footprint is
    'The enclosed 2D area. NULL when the lines do not close, POLYGON EMPTY when the input is empty.';
comment on column topogdb.footprint_facts.areas is
    'Number of disjoint parts of the footprint. 0 when none was built.';
comment on column topogdb.footprint_facts.holes is
    'Interior rings, summed over every part.';
comment on column topogdb.footprint_facts.curves_all_used is
    'False when some line does not lie on the footprint boundary: a dangle, or an inner ring '
    'that failed to close and was discarded.';


do $$
begin
    if not exists (
        select 1
        from pg_type t
        join pg_namespace n on n.oid = t.typnamespace
        where n.nspname = 'topogdb'
          and t.typname = 'footprint_measure'
    ) then
        create type topogdb.footprint_measure as (
            row_exists       boolean,
            members          integer,
            included         integer,
            linework_simple  boolean,
            footprint        geometry,
            areas            integer,
            holes            integer,
            curves_all_used  boolean,
            unused           jsonb
        );
    end if;
end;
$$;

comment on type topogdb.footprint_measure is
    'All measured facts needed to judge one derived footprint without rebuilding it.';


create or replace function topogdb.build_footprint(lines geometry)
returns topogdb.footprint_facts
language plpgsql
immutable
parallel safe
as $$
declare
    flat geometry;
    f    topogdb.footprint_facts;
begin
    if lines is not null then
        if GeometryType(lines) <> 'MULTILINESTRING' then
            raise exception 'build_footprint expects MULTILINESTRING, got %', GeometryType(lines)
                using errcode = 'XX000',
                      hint = 'Gather members with ST_Collect over ST_Dump of each member geometry.';
        end if;
        if (select coalesce(bool_or(ST_IsEmpty(part.geom)), false) from ST_Dump(lines) part) then
            raise exception 'build_footprint received a MULTILINESTRING with an empty member'
                using errcode = 'XX000',
                      hint = 'Borderlines of footprint cannot be empty.';
        end if;
    end if;

    -- Force2D because ST_Node matches on XY and would otherwise carry an arbitrary Z.
    flat := ST_Force2D(lines);

    f.footprint := ST_BuildArea(ST_Node(flat));
    f.areas           := 0;
    f.holes           := 0;
    f.curves_all_used := false;

    if f.footprint is not null and not ST_IsEmpty(f.footprint) then
        -- ST_BuildArea is not expected to return invalid geometries when
        -- input is noded
        if not ST_IsValid(f.footprint) then
            raise exception 'build_footprint produced an invalid footprint: %',
                            ST_IsValidReason(f.footprint)
                using errcode = 'XX000';
        end if;

        f.areas := ST_NumGeometries(f.footprint);
        f.holes := (
            select coalesce(sum(ST_NumInteriorRings(part.geom)), 0)
            from (select (ST_Dump(f.footprint)).geom) part
        );
        f.curves_all_used := ST_CoveredBy(flat, ST_Boundary(f.footprint));
    end if;

    return f;
end;
$$;

comment on function topogdb.build_footprint(geometry) is
    'Build the 2D footprint enclosed by a set of boundary lines, and return their footprint_facts. '
    'Precondition: input must be NULL or MULTILINESTRING, and non-empty members must all be present. '
    'The lines arrive collected into one geometry so order and direction do not matter. '
    'Z-coordinate is dropped if it exists. '
    'Raises XX000 if the built footprint is invalid, which noded linework never produces.';
