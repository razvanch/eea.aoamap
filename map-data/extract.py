#!/usr/bin/env python
""" Extract
"""
import sys
from collections import namedtuple
import json
from osgeo import ogr
from osgeo import gdal
import dp

gdal.UseExceptions()

def get_properties(feature, encoding):
    """ Properties
    """
    fields = {}
    for field in range(feature.GetFieldCount()):
        name = feature.GetFieldDefnRef(field).GetName().decode(encoding)
        value = feature.GetFieldAsString(field).decode(encoding)
        fields[name] = value
    return fields

def get_features(in_file_path, encoding):
    """ Features
    """
    shapefile = ogr.Open(in_file_path)
    layer = shapefile.GetLayer(0)

    feature = layer.GetNextFeature()
    while feature:
        properties = get_properties(feature, encoding)
        geometry = json.loads(feature.GetGeometryRef().ExportToJson())
        yield properties, geometry
        feature = layer.GetNextFeature()

pick_countries = ['Albania', 'Andorra', 'Armenia', 'Austria', 'Azerbaijan',
'Belarus', 'Belgium', 'Bosnia and Herzegovina', 'Bulgaria', 'Croatia',
'Cyprus', 'Czech Republic', 'Denmark', 'Estonia', 'Finland', 'France',
'Georgia', 'Germany', 'Greece', 'Hungary', 'Iceland', 'Ireland', 'Italy',
'Kazakhstan', 'Kyrgyzstan', 'Latvia', 'Liechtenstein', 'Lithuania',
'Luxembourg', 'Former Yugoslav Republic of Macedonia', 'Malta',
'Republic of Moldova', 'Monaco', 'Montenegro', 'the Netherlands', 'Norway',
'Poland', 'Portugal', 'Romania', 'Russian Federation', 'San Marino', 'Serbia',
'Slovakia', 'Slovenia', 'Spain', 'Sweden', 'Switzerland', 'Tajikistan',
'Turkey', 'Turkmenistan', 'Ukraine', 'the United Kingdom', 'Uzbekistan',
'Kosovo under un security council 1244/9950']

rename_map = {
    "Bosnia and Herz.": 'Bosnia and Herzegovina',
    "Czech Rep.": 'Czech Republic',
    "Macedonia": 'Former Yugoslav Republic of Macedonia',
    "Moldova": 'Republic of Moldova',
    "Netherlands": 'the Netherlands',
    "Russia": 'Russian Federation',
    "United Kingdom": 'the United Kingdom',
    "Kosovo": 'Kosovo under un security council 1244/9950',
    "FYR of Macedonia": "Former Yugoslav Republic of Macedonia",
}

pick_regions = {
    "EEA member countries":
        ["Austria", "Belgium", "Bulgaria", "Cyprus", "Czech Republic",
        "Denmark", "Estonia", "Finland", "France", "Germany", "Greece",
        "Hungary", "Iceland", "Ireland", "Italy", "Latvia", "Liechtenstein",
        "Lithuania", "Luxembourg", "Malta", "the Netherlands", "Norway",
        "Poland", "Portugal", "Romania", "Slovakia", "Slovenia", "Spain",
        "Sweden", "Switzerland", "Turkey", "the United Kingdom"],
    "Western Balkans":
        ["Albania", "Bosnia and Herzegovina", "Croatia",
        "Former Yugoslav Republic of Macedonia",
        "Kosovo under un security council 1244/9950", "Montenegro", "Serbia"],
    "Eastern Europe":
        ["Belarus", "Republic of Moldova", "Ukraine"],
    "Russian Federation":
        ["Russian Federation"],
    "Central Asia":
        ["Kazakhstan", "Kyrgyzstan", "Tajikistan", "Turkmenistan",
        "Uzbekistan"],
    "Caucasus":
        ["Armenia", "Azerbaijan", "Georgia"],
}

def number_of_points(polygon):
    """ Points
    """
    return sum(len(ring) for ring in polygon)

def simplify_poly(poly):
    """ Simplify
    """
    new_poly = []
    for idx, ring in enumerate(poly):
        if len(ring) < 25:
            tolerance = 0.01
        elif len(ring) < 50:
            tolerance = 0.03
        else:
            tolerance = 0.12
        new_ring = dp.simplify_points(ring, tolerance)
        if len(new_ring) < 4:
            if idx == 0:
                return []

        else:
            new_poly.append(new_ring)

    return new_poly

def points_in_geometry(geometry):
    """ Points
    """
    if geometry['type'] == 'Polygon':
        return sum(len(ring) for ring in geometry['coordinates'])
    elif geometry['type'] == 'MultiPolygon':
        return sum(sum(len(ring) for ring in poly)
                   for poly in geometry['coordinates'])
    else:
        raise ValueError('Unknown geometry type %r' % geometry['type'])

def simplify_geometry(geometry):
    """ Simplify geometry
    """
    if geometry['type'] == 'Polygon':
        geometry['coordinates'] = simplify_poly(geometry['coordinates'])

    elif geometry['type'] == 'MultiPolygon':
        geometry['coordinates'] = [simplify_poly(p)
                                   for p in geometry['coordinates']
                                   if simplify_poly(p) is not None]
        geometry['coordinates'].sort(key=number_of_points, reverse=True)

    else:
        raise ValueError('Unknown geometry type %r' % geometry['type'])

    if not geometry['coordinates']:
        raise ValueError("polygon removed")

def area(ring):
    """ Area
    """
    return sum(ring[i][0] * ring[i+1][1] - ring[i+1][0] * ring[i][1]
               for i in xrange(len(ring)-1))

def normalize_ring(ring):
    """ Ring
    """
    if area(ring) < 0:
        ring.reverse()

def deduplicate(ring):
    """ Remove duplicates
    """
    while True:
        for i in range(len(ring)-1):
            if ring[i] == ring[i+1]:
                del ring[i+1]
            elif i > 0 and ring[i-1] == ring[i+1]:
                del ring[i+1]
                del ring[i]
            else:
                continue
            if ring[-1] != ring[0]:
                ring.append(ring[0])
            break

        else:
            # try the ends
            if ring[1] == ring[-2]:
                del ring[-1]
                del ring[0]

            else:
                # ok, no more duplicates left
                return

def extract_hole(ring):
    """ Hole
    """
    seen = {}
    for j, p in enumerate(ring[:-1]):
        if p in seen:
            i = seen[p]
            new_hole = ring[i:j+1]
            ring[i+1:j] = []
            return new_hole
        seen[p] = j

RingMatch = namedtuple('RingMatch', 'i ring_m m')

def match_any(ring_a, some_rings):
    """ Match
    """
    points_a = set(ring_a)
    for ring_m in some_rings:
        for m, p in enumerate(ring_m):
            if p in points_a:
                return RingMatch(ring_a.index(p), ring_m, m)

def splice_rings(ring_a, idx_a, ring_b, idx_b):
    """ Splice rings
    """
    ring_a[idx_a:idx_a] = ring_b[idx_b:] + ring_b[:idx_b]

def merge_multipolygon(geometry):
    """ Merge
    """
    if geometry['type'] != 'MultiPolygon':
        raise ValueError('Unknown geometry type %r' % geometry['type'])


    initial_polys = []
    for poly_n in geometry['coordinates']:
        ring_n = [tuple(point) for point in poly_n[0]]
        del ring_n[-1]
        if (-7.451245, 54.877116) not in ring_n: # TODO wtf?
            normalize_ring(ring_n)
        holes_n = [map(tuple, hole) for hole in poly_n[1:]]
        initial_polys.append((ring_n, holes_n))

    joined_rings = []
    def new_island():
        """ Island
        """
        ring, holes = initial_polys.pop()
        ring.append(ring[0])
        joined_rings.append((ring, holes))
        return ring, holes


    ring, holes = new_island()

    while initial_polys:
        # try to join one ring
        match = match_any(ring, (ring_n for ring_n, holes_n in initial_polys))

        if match is None:
            # no more rings can be joined; start a new island
            ring, holes = new_island()
            continue

        splice_rings(ring, match.i, match.ring_m, match.m)

        for ring_n, holes_n in initial_polys:
            if ring_n == match.ring_m:
                holes.extend(holes_n)
                initial_polys.remove((ring_n, holes_n))
                break
        else:
            raise ValueError("can't find ring any more!")

        while True:
            deduplicate(ring)
            hole = extract_hole(ring)
            if hole is None:
                break
            holes.append(hole)


    # now, try to fill holes
    while True:
        for ring, holes_of_ring in joined_rings:
            if holes_of_ring:
                continue # hole filler containing holes? too complex.

            for _ignored_ring, holes in joined_rings:
                match = match_any(ring, holes)
                if match is not None:
                    if set(ring) == set(match.ring_m): # only exact matches
                        break
            else:
                continue # `ring` does not fill any `holes`

            holes.remove(match.ring_m)
            joined_rings.remove((ring, holes_of_ring))
            break

        else:
            break # no more holes to fill

    return {
        'type': 'MultiPolygon',
        'coordinates': [[ring]+holes for ring, holes in joined_rings],
    }

def Feature(geometry, **kwargs):
    """ Feature
    """
    return {
        'geometry': geometry,
        'properties': kwargs,
    }

def geojson(features):
    """ GeoJSON
    """
    return {
        'type': "FeatureCollection",
        'features': features,
    }

def extract_countries(in_file_path):
    """ Extract countries
    """
    for properties, geometry in get_features(in_file_path, 'latin-1'):
        name = properties['NAME']
        name = rename_map.get(name, name)
        if name not in pick_countries:
            continue
        pick_countries.remove(name)

        yield Feature(geometry, name=name, countries=[name])

    if pick_countries:
        raise ValueError("Countries not picked: %r" % pick_countries)

def extract_regions(countries):
    """ Regions
    """
    geometry_by_country = dict((f['properties']['name'], f['geometry'])
                                for f in countries)
    for region_name, country_names in pick_regions.iteritems():
        polygons = []
        for name in country_names:
            country_geom = geometry_by_country[name]
            if country_geom['type'] == 'MultiPolygon':
                polygons.extend(country_geom['coordinates'])
            else:
                polygons.append(country_geom['coordinates'])
        geometry = {
            'type': 'MultiPolygon',
            'coordinates': polygons,
        }
        yield Feature(merge_multipolygon(geometry),
                      name=region_name,
                      countries=country_names)


def countries_main(args):
    """ Main countries
    """
    countries = list(extract_countries(args.shapefile))
    json.dump(geojson(countries), sys.stdout, indent=2)


def regions_main(args):
    """ Main regions
    """
    countries = list(extract_countries(args.shapefile))
    regions = list(extract_regions(countries))
    json.dump(geojson(regions), sys.stdout, indent=2)


def simplify_main(args):
    """ Simplify main
    """
    features = json.load(sys.stdin)['features']
    for f in features:
        try:
            simplify_geometry(f['geometry'])
        except ValueError, e:
            raise ValueError("%r %r", (e, f['properties']))
    json.dump(geojson(features), sys.stdout)

def feature_area(feature):
    """ Feature areas
    """
    geometry = feature['geometry']
    if geometry['type'] != 'Polygon':
        raise ValueError('Unknown geometry type %r' % geometry['type'])
    return area(geometry['coordinates'][0])

def country_bodies_main(args):
    """ Bodies
    """
    features = json.load(sys.stdin)['features']

    for f in features:
        geometry = f['geometry']

        if geometry['type'] == 'MultiPolygon':
            ordered_polys = sorted(geometry['coordinates'],
                                   key=number_of_points, reverse=True)
            geometry['coordinates'] = ordered_polys[0]
            geometry['type'] = 'Polygon'

    features.sort(key=feature_area)

    json.dump(geojson(features), sys.stdout, indent=2)


def parse_args():
    """ Parse args
    """
    import argparse
    parser = argparse.ArgumentParser()

    subparsers = parser.add_subparsers()

    countries_parser = subparsers.add_parser('countries')
    countries_parser.add_argument('shapefile')
    countries_parser.set_defaults(subcommand=countries_main)

    regions_parser = subparsers.add_parser('regions')
    regions_parser.add_argument('shapefile')
    regions_parser.set_defaults(subcommand=regions_main)

    simplify_parser = subparsers.add_parser('simplify')
    simplify_parser.set_defaults(subcommand=simplify_main)

    country_bodies_parser = subparsers.add_parser('country_bodies')
    country_bodies_parser.set_defaults(subcommand=country_bodies_main)

    return parser.parse_args()


def main():
    """ Main
    """
    args = parse_args()
    args.subcommand(args)


if __name__ == "__main__":
    main()
