# -*- coding: utf-8 -*-
"""
/***************************************************************************
 RasterCutter
                                 A QGIS plugin
 This Plugin allows the export of JPG files with a JPGL Sidecar file.
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2022-04-26
        git sha              : $Format:%H$
        copyright            : (C) 2022 by IFS Institute for Software
        email                : feedback.ifs@ost.ch
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from PyQt5.QtCore import QSize
from PyQt5.QtGui import QCursor, QImage, QColor, QPainter
from PyQt5.QtWidgets import QMenu, QFileDialog
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
import qgis.core
from qgis.core import (QgsProcessingParameterDefinition,
                       QgsProcessingParameters,
                       QgsProject,
                       QgsMapSettings,
                       QgsMapLayer,
                       QgsRectangle,
                       QgsMapRendererCustomPainterJob,
                       QgsCoordinateReferenceSystem,
                       QgsCoordinateTransform,
                       QgsReferencedRectangle,
                       QgsMapLayerProxyModel)

# Initialize Qt resources from file resources.py
from .resources import *
# Import the code for the dialog
from .raster_cutter_dialog import RasterCutterDialog
import os.path
from osgeo import gdal, ogr


# TODO logo
# TODO help button
# TODO remove test button
# TODO maybe allow user to set resolution and aspect ratio

class RasterCutter:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'RasterCutter_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&Raster Cutter')

        # Check if plugin was started the first time in current QGIS session
        # Must be set in initGui() to survive plugin reloads
        self.first_start = None

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('RasterCutter', message)

    def add_action(
            self,
            icon_path,
            text,
            callback,
            enabled_flag=True,
            add_to_menu=True,
            add_to_toolbar=True,
            status_tip=None,
            whats_this=None,
            parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/raster_cutter/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Export JPG + JPGL'),
            callback=self.run,
            parent=self.iface.mainWindow())

        # will be set False in run()
        self.first_start = True

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&Raster Cutter'),
                action)
            self.iface.removeToolBarIcon(action)

    def run(self):
        """Run method that performs all the real work"""

        # Create the dialog with elements (after translation) and keep reference
        # Only create GUI ONCE in callback, so that it will only load when the plugin is started
        if self.first_start:
            self.first_start = False
            self.dlg = RasterCutterDialog()

        self.dlg.file_dest_field.setFilePath(os.path.expanduser("~"))
        widget_init(self)

        # show the dialog
        self.dlg.show()
        # Run the dialog event loop
        result = self.dlg.exec_()
        # See if OK was pressed
        if result:
            directory_url = self.dlg.file_dest_field.filePath()  # read the file location from form label
            selected_layer = self.dlg.layer_combobox.currentLayer()
            src = gdal.Open(selected_layer.dataProvider().dataSourceUri(), gdal.GA_ReadOnly)
            print("Metadata")
            print(src.GetMetadata())
            src_proj = src.GetProjection()
            print("Projecttion")
            print(src_proj)
            dst_proj = gdal.Translate(directory_url, src, format="JPEG", options="-co WORLDFILE=YES")
            print(dst_proj)

            if self.dlg.lexocad_checkbox.isChecked():  # if "Generate Lexocad support files" box is checked
                print("todo")


def widget_init(self):
    # input layer init
    self.dlg.layer_combobox.setShowCrs(True)
    on_layer_changed(self)

    # extentbox init
    self.dlg.extent_box.setOriginalExtent(originalExtent=self.dlg.layer_combobox.currentLayer().extent(),
                                          originalCrs=QgsCoordinateReferenceSystem.fromEpsgId(2056))
    self.dlg.extent_box.setCurrentExtent(currentExtent=self.iface.mapCanvas().extent(),
                                         currentCrs=QgsCoordinateReferenceSystem.fromEpsgId(2056))
    self.dlg.extent_box.setOutputCrs(QgsCoordinateReferenceSystem.fromEpsgId(2056))

    self.dlg.test_btn.clicked.connect(lambda: print(os.path.expanduser('~')))


def on_layer_changed(self):
    self.dlg.extent_box.setOriginalExtent(originalExtent=self.dlg.layer_combobox.currentLayer().extent(),
                                          originalCrs=QgsCoordinateReferenceSystem.fromEpsgId(2056))
    print("layer changed")


def convert_extent_crs_to_2056(extent):
    # Converts an extent (CRS of project) to CH1903+ / LV95, as required by lexocad
    src_crs = QgsCoordinateReferenceSystem(QgsProject.instance().crs())
    dst_crs = QgsCoordinateReferenceSystem.fromEpsgId(2056)
    coords_transform = QgsCoordinateTransform(src_crs, dst_crs, QgsProject.instance())
    return coords_transform.transform(extent)


def convert_extent_crs_to_layer(extent, selected_layer):
    # Converts an extent (CH1903+ / LV95) to match CRS of layer, as required to save image
    src_crs = QgsCoordinateReferenceSystem.fromEpsgId(2056)
    dst_crs = QgsCoordinateReferenceSystem(selected_layer.crs())
    coords_transform = QgsCoordinateTransform(src_crs, dst_crs, QgsProject.instance())
    return coords_transform.transform(extent)


def clip_extent_to_square(extent):
    width = extent.xMaximum() - extent.xMinimum()
    height = extent.yMaximum() - extent.yMinimum()
    # get the value of either extent width or height, whichever is longest
    longer_side = width
    if height > longer_side:
        longer_side = height
    center_x = extent.center().x()
    center_y = extent.center().y()
    # return a square extent, with a height and with of the longer side and a center of the supplied extent
    return QgsRectangle(
        center_x - (longer_side / 2),
        center_y - (longer_side / 2),
        center_x + (longer_side / 2),
        center_y + (longer_side / 2)
    )


def round_extent(extent):
    return QgsRectangle(
        round(extent.xMinimum()),
        round(extent.yMinimum()),
        round(extent.xMaximum()),
        round(extent.yMaximum()),
    )


def save_image(selected_layer, extent, directory_url):
    img = QImage(QSize(2000, 2000), QImage.Format_ARGB32_Premultiplied)
    # set background color
    color = QColor(255, 255, 255, 255)
    img.fill(color.rgba())
    # create painter with antialiasing
    p = QPainter()
    p.begin(img)
    p.setRenderHint(QPainter.Antialiasing)
    # create map settings
    ms = QgsMapSettings()
    ms.setBackgroundColor(color)
    # set layers to render
    ms.setLayers([selected_layer])
    # rect.scale(1.1)
    ms.setExtent(extent)
    ms.setOutputSize(img.size())
    # setup qgis map renderer
    render = QgsMapRendererCustomPainterJob(ms, p)
    render.start()
    render.waitForFinished()
    p.end()
    img.save(directory_url)


def generate_worldfile(directoryUrl):
    print("unimplemented")


def generate_lexocad_files(directoryUrl, extent):
    # TODO test with other crs's
    # TODO are decimal places supported?
    width = extent.xMaximum() - extent.xMinimum()
    height = extent.yMaximum() - extent.yMinimum()
    with open(directoryUrl + "l", 'w') as f:
        f.write(
            str(int(extent.xMinimum())) + "\n" +
            str(int(extent.yMinimum())) + "\n" +
            str(int(width)) + "\n" +
            str(int(height)) + "\n" +
            "\n" +
            "# cadwork swisstopo" + "\n" +
            "# " + str(extent.xMinimum()) + " " + str(extent.yMinimum()) + "\n" +
            "# " + str(width) + " " + str(height) + "\n" +
            "# projection: EPSG:2056 - CH1903+ / LV95"
        )


def throw_error(message):
    # TODO improve error handling
    print(message)
