# Works with protobuf 6.30+ and 7.x (patches removed MessageFactory.GetPrototype)

import google.protobuf.message_factory as _mf

# https://protobuf.dev/news/v30/#remove-deprecated
if not hasattr(_mf.MessageFactory, "GetPrototype"):
    _mf.MessageFactory.GetPrototype = staticmethod(_mf.GetMessageClass)
