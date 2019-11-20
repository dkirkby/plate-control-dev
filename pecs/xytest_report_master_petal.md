### PC0<%{0}%>: ``<%=len(data.posids_pc[{0}])%>`` positioners tested

```python name='pc{0:02} temp, grade distribution', echo=False
if data.db_telemetry_available:
    plot_posfid_temp(pcid={0})
else:
    print('DB telemetry query unavailable on this platform\n')
grade_counts = plot_grade_dist(pcid={0})
grades_pc = data.grade_df[data.grade_df['PCID'] == {0}]
posids_grade = {{}}
for grade in grades:
	mask = grades_pc['grade'] == grade
	posids_grade[grade] = sorted(data.grade_df[mask].index)
```

```python name='pc{0:02} median stats by grade', echo=False, caption='Median of error measures by grades'
dfs = []
for grade in grades:
	df = grades_pc[grades_pc['grade']==grade]
	dfs.append(df.median())
pd.DataFrame(dfs, index=grades).iloc[:, :5]
```

```python, name='pc{0:02} error distribution', echo=False, width='linewidth'
plot_error_dist(pcid={0})
n_abnormal = (df_abnormal['PCID']=={0}).index.droplevel(0).unique().size
```

##### Abnormal status: ``<%=n_abnormal%>`` positioners
```python name='pc{0:02} abnormal flags', echo=False, results='verbatim'
abnormal_pc = abnormal_pos_df(pcid={0})
gradedf_pc = data.gradedf[data.gradedf['PCID']=={0}]
gradedf_pc_maxb = gradedf_pc[gradedf_pc['err_0_max']>200]
gradedf_pc_rmsc = gradedf_pc[gradedf_pc['err_corr_rms']>30]
posids_exclude = sorted((set(abnormal_pc.index) | set(gradedf_pc_maxb.index)
                  | set(gradedf_pc_rmsc)))
abnormal_pc.reset_index().astype(int, errors='ignore')
```

##### Max blind move error > 200 μm: ``<%=len(gradedf_pc_maxb)%>`` positioners
```python name='pc{0:02} max blind', echo=False
gradedf_pc_maxb.iloc[:, :6].reset_index().astype(int, errors='ignore')
```

##### RMS corrective move error > 30 μm: ``<%=len(gradedf_pc_rmsc)%>`` positioners
```python name='pc{0:02} rms corr', echo=False
gradedf_pc_rmsc.iloc[:, :6].reset_index().astype(int, errors='ignore')
```

##### Move errors by targets excluding ``<%=len(posids_exclude)%>`` outliers (μm)
```python name='pc{0:02} errors by targets', echo=False
movedf_filtered = (data.movedf.drop(posids_exclude, level=1)
                   [[col for col in data.movedf.columns if 'err_xy_' in col]]
                   * 1000)  # convert to microns
max_df = movedf_filtered.max(axis=0, level=0)
# mean_df = movedf_filtered.mean(axis=0, level=0)
rms_df = np.sqrt(np.square(movedf_filtered).mean(axis=0, level=0))
df = max_df.join(rms_df, lsuffix='_max', rsuffix='_rms')
df.rename(columns={{col: col.replace('err_xy_', 'submove_') for col in df.columns}},
          inplace=True)
df.reset_index().astype(int, errors='ignore')
```

##### Move errors by submoves excluding ``<%=len(posids_exclude)%>`` outliers (μm)

```python name='pc{0:02} errors by submoves', echo=False
max_series = movedf_filtered.max(axis=0)
rms_series = np.sqrt(np.square(movedf_filtered).mean(axis=0))
median_series = movedf_filtered.mean(axis=0)
pd.DataFrame([max_series, rms_series, median_series],
             index=['max', 'rms', 'median']).T.astype(int, errors='ignore')
```

##### Grade A: ``<%=grade_counts['A']%>`` positioners
```python, name='pc{0:02} grade A error distribution', echo=False, width='linewidth', results='hidden'
if grade_counts['A'] > 0:
	plot_error_dist(pcid={0}, grade='A')
```
``<%=posids_grade['A']%>``

##### Grade B: ``<%=grade_counts['B']%>`` positioners
```python, name='pc{0:02} grade B error distribution', echo=False, width='linewidth', results='hidden'
if grade_counts['B'] > 0:
	plot_error_dist(pcid={0}, grade='B')
```
``<%=posids_grade['B']%>``

##### Grade C: ``<%=grade_counts['C']%>`` positioners
```python, name='pc{0:02} grade C error distribution', echo=False, width='linewidth', results='hidden'
if grade_counts['C'] > 0:
	plot_error_dist(pcid={0}, grade='C')
```
``<%=posids_grade['C']%>``

##### Grade D: ``<%=grade_counts['D']%>`` positioners
```python, name='pc{0:02} grade D error distribution', echo=False, width='linewidth', results='hidden'
if grade_counts['D'] > 0:
	plot_error_dist(pcid={0}, grade='D')
```
``<%=posids_grade['D']%>``

##### Grade F: ``<%=grade_counts['F']%>`` positioners
```python, name='pc{0:02} grade F error distribution', echo=False, width='linewidth', results='hidden'
if grade_counts['F'] > 0:
	plot_error_dist(pcid={0}, grade='F')
```
``<%=posids_grade['F']%>``

##### Grade N/A: ``<%=grade_counts['N/A']%>`` positioners
``<%=posids_grade['N/A']%>``
