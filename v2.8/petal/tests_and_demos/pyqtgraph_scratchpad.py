# scratchpad for some pyqtgraph basic usage

# highly useful, to run "python -m pyqtgraph.examples"

# when running in Spyder, note necessity to set Tools > Preferences > IPython console > Graphics to "Automatic"

# uses some points from poscollider
import pyqtgraph as pg
w = pg.GraphicsWindow()
p = w.addPlot(title='hello')
q = pg.PlotDataItem(P3.points[0],P3.points[1])
p.addItem(q)
r = pg.PlotDataItem(P4.points[0],P4.points[1])
p.addItem(r)
s = pg.PlotDataItem(P1.points[0],P1.points[1])
p.addItem(s)
s.setData(P2.points[0],P2.points[1])
q.setData(P2.points[0],P2.points[1])
r.setData(P2.points[0],P2.points[1])
p.removeItem(q)
p.removeItem(r)
p.removeItem(s)
p.addItem(s)

import pyqtgraph.exporters
from pyqtgraph import QtGui
QtGui.QApplication.processEvents()
exporter = pg.exporters.ImageExporter(p)
# exporting images has a bug that needs a workaround, related to the export size. see below
# c.f. https://stackoverflow.com/questions/48824070/pyqtgraphs-exporter-shifts-plot-components
exporter.parameters()['width'] = 2048
new_height = int(exporter.parameters()['height'])
exporter.params.param('height').setValue(new_height, blockSignal=exporter.heightChanged)
exporter.export('hello.png')
