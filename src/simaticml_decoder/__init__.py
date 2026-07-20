"""simaticml-decoder — SimaticML LAD/FBD -> readable SCL + JSON metadata sidecar.

Pipeline (three independently testable phases):

    parse.py   XML            -> model.*   (faithful, dumb mirror of the XML syntax)
    fold.py    model.*        -> ir.*      (semantics: boolean tree + assignments)
    emit.py    ir.*           -> SCL text + JSON sidecar

Supporting modules: instructions.py (part catalog, data not logic),
operand.py (Access -> display string), scl_reconstruct.py (SCL networks).
"""

__version__ = "0.2.3"
