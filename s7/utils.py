from inspect import signature

# utility
def execute_function(d):
    tuples = [(k,v()) for k,v in d['args'].items()] 
    return (globals()[d['fn']](**dict(tuples)))

# utility function to register a python function
def register_function(graph, func):
    decl = {'fn': func.__name__, 'args': {}}
    graph.append((func.__name__, 'is', 'Function'))            
    sig = signature(func)
    for p in dict(sig.parameters).keys():    
        graph.append((p, 'is', 'InputParameter'))
        graph.append((func.__name__, 'has_input', p))
    return decl
        
        
# utility function to set a getter function
def set_getter(graph, decl, parameter, func):
    graph.append((parameter, 'has_get', func))
    decl['args'].update({parameter: func})