import { feature } from "topojson-client";
import topo from "world-atlas/countries-110m.json";

export const countries = feature(topo, topo.objects.countries);
