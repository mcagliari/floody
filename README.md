# floody
forecasting flood losses and savings for cities

## Data
The processed data files (`floody.*.hdf5`, `tl_2022_us_zcta520/`) are not in the repo.
`floody.data` reads them from the directory named by the environment variable
`FLOODY_DATA` and raises an error if it is not set, e.g.

```bash
export FLOODY_DATA=/path/to/floody/data
# or, per conda environment:
conda env config vars set FLOODY_DATA=/path/to/floody/data -n <env>
```
