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
            sections_doubled  double precision,
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
comment on column topogdb.footprint_facts.sections_doubled is
    'Length covered by more than one line. Measured from the input lines directly and is therefore '
    'independent of the footprint being closed.';
comment on column topogdb.footprint_facts.areas is
    'Number of disjoint parts of the footprint. 0 when none was built.';
comment on column topogdb.footprint_facts.holes is
    'Interior rings, summed over every part.';
comment on column topogdb.footprint_facts.curves_all_used is
    'False when some line does not lie on the footprint boundary: a dangle, or an inner ring '
    'that failed to close and was discarded.';


create or replace function topogdb.build_footprint(lines geometry)
returns topogdb.footprint_facts
language plpgsql
immutable
parallel safe
as $$
declare
    flat geometry := ST_Force2D(lines);  -- Force 2d as ST_NODE matches XY and picks arbitrary z
    f    topogdb.footprint_facts;
begin
    f.sections_doubled := coalesce(ST_Length(flat), 0)
                      - coalesce(ST_Length(ST_UnaryUnion(flat)), 0);

    f.footprint := ST_BuildArea(ST_Node(flat));
    f.areas           := 0;
    f.holes           := 0;
    f.curves_all_used := false;

    if f.footprint is not null and not ST_IsEmpty(f.footprint) then
        f.areas           := ST_NumGeometries(f.footprint);
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
    'The lines arrive collected into one geometry so order and direction do not matter. '
    'Z-coordinate is dropped if it exists. ';
