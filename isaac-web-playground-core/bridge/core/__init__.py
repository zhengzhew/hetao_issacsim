"""Isaac Web Playground bridge, runtime core (no MicroDuck).

app_context creates the Isaac SimulationApp and has to be imported before
anything touches omni.*/isaacsim.* at module scope. Every other module here
only touches those inside function bodies, so importing this package is
enough to get the ordering right.
"""
