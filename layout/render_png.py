import klayout.lay as lay, sys
v = lay.LayoutView()
v.load_layout(sys.argv[1], 0)
v.load_layer_props("/foss/pdks/gf180mcuD/libs.tech/klayout/tech/gf180mcu.lyp")
v.max_hier(); v.zoom_fit()
v.set_config("background-color", "#ffffff")
v.save_image(sys.argv[2], 2400, 1150)
