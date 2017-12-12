import os

basepath = os.path.abspath('../')
logdir = os.path.abspath(os.path.join(basepath,'positioner_logs'))
allsetdir = os.path.abspath(os.path.join(basepath,'fp_settings'))
if not os.path.exists(logdir):
    os.makedirs(logdir)
    os.makedirs(os.path.join(logdir,'move_logs'))
    os.makedirs(os.path.join(logdir,'test_logs'))
    os.makedirs(os.path.join(logdir,'pos_logs'))
if not os.path.exists(allsetdir):
    os.makedirs(allsetdir)
if 'POSITIONER_LOGS_PATH' not in os.environ:
    os.environ['POSITIONER_LOGS_PATH'] = logdir
if 'PETAL_PATH' not in os.environ:
    os.environ['PETAL_PATH'] = basepath
if 'FP_SETTINGS_PATH' not in os.environ:
    os.environ['FP_SETTINGS_PATH'] = allsetdir
import time
import numpy as np
import pickle as pkl
import posmodel
import matplotlib.pyplot as plt
import pdb
from itertools import count
# speciality
#from collections import deque
#import heapq
from heapq import heappush, heappop

# Which file to load
#vers = int(np.random.randint(1,3,1))
#tolerance_xy = 1

#heuristic = 'euclidean'#'phi


###########################
# Actual Code
###########################
def get_tp_distance(tgrid,pgrid,target,heuristic='phi'):
    # All heuristics need dtheta except for the phi heuristic
    # Similarly for theta heuristic
    if heuristic.lower() != 'phi':
        dtheta = tgrid-(target[0]+np.max(tgrid)-np.min(tgrid))
    if heuristic.lower() != 'theta':
        dphi = pgrid-(target[1]+np.max(pgrid)-np.min(pgrid))
        
    if heuristic.lower() == 'phi':
        return dphi
    elif heuristic.lower() == 'theta':
        return dtheta
    elif heuristic.lower() == 'euclidean':
        return np.hypot(dtheta.ravel(),dphi.ravel()).reshape(tgrid.shape) 
    elif heuristic.lower() == 'manhattan':
        return dphi + dtheta
    else:
        print('Heuristic did not match any available methods in get_tp_distance')
        return np.zeros(tgrid.shape)



def build_bool_grid(xs,ys,xns,yns,tbods,pbods,tolerance):
    bool_map = np.zeros(xs.size).astype(bool)
    is_bad_row = np.zeros(xs.shape[0]).astype(bool)

    tbodxs = tbods[:,0,:]
    tbodys = tbods[:,1,:]
    #pbodxs = pbods[:,:,0,:]
    #pbodys = pbods[:,:,1,:]    
    
    pbod_xravels = []
    pbod_yravels = []
    for i in range(pbods.shape[3]):
        pbod_xravels.append(pbods[:,:,0,i].ravel())
        pbod_yravels.append(pbods[:,:,1,i].ravel())
        
    #xravel = xs.ravel()
    #yravel = ys.ravel()
    #theta_tolerance = 0.1*tolerance
    #pbod_xravels.append(xravel)
    #pbod_yravels.append(yravel)
    #all_xravels = np.asarray(pbod_xravels)
    #all_yravels = np.asarray(pbod_yravels)

    for x,y in zip(xns,yns): 
        for xrav,yrav in zip(pbod_xravels,pbod_yravels):
            bool_temp = (  np.hypot(xrav-x,yrav-y) < tolerance  )
            #pdb.set_trace()
            bool_map = ( bool_map | bool_temp )
        for i in range(tbodxs.shape[-1]):
            temp_rows = ( np.hypot( tbodxs[:,i]-x, tbodys[:,i]-y ) < tolerance )
            is_bad_row = ( is_bad_row | temp_rows )

    outmap = bool_map.reshape(xs.shape)
    outmap[is_bad_row,:] = True#False
    return outmap



def build_adjlist(boolgrid,distances_tp_start,distances_tp_goal):
    dtps = distances_tp_start
    dtpg = distances_tp_goal
    # Get size of grid
    nrows = boolgrid.shape[0]
    ncols = boolgrid.shape[1]
    # expand bool grid to avoid edges more easily
    expanded_bool = np.ones((nrows+2,ncols+2)).astype(bool)
    expanded_bool[1:-1,1:-1] = boolgrid
    # Create oned iterable of grid
    allis,alljs = np.meshgrid(np.arange(nrows),np.arange(ncols))
    # Instantiate adjacency list
    #pdb.set_trace()
    adj_list = {}
    # Do the loop, assign neighbors to each node with node index tup as key    
    for i,j in zip(allis.ravel(),alljs.ravel()):
        if expanded_bool[i+1,j+1]:
            continue
        possible_neighbors = [ (i-1, j-1) ,  (i-1,j) , (i-1, j+1) ,\
                               (i,   j-1) ,            (i,   j+1) ,\
                               (i+1, j-1) ,  (i+1,j) , (i+1, j+1)  ]
        adj_list[(i,j)] = [ ((ip,jp),{'dist_to_start':dtps[ip,jp],'dist_to_goal':dtpg[ip,jp]}) \
                                        for ip,jp in possible_neighbors \
                                            if not expanded_bool[ip+1,jp+1]   ]                          
    return adj_list


def get_final_path(visited,beginning,intersecting_node,orientation='start'):
    path = []
    current_node = intersecting_node
    while current_node != None:
        path.append(current_node)
        if current_node == beginning:
            break
        current_node = visited[current_node]
    if orientation.lower() == 'start':
        path = path[::-1]
    return path




def find_path(graph, start, goal,start_to_goal_dist,weight_multiplier,verbose=False):
    node_s = start
    node_g = goal
    if node_s == node_g or node_s not in graph.keys() or node_g not in graph.keys():
        print("Something wrong with nodes, so returning without performing pathfinding")
        #pdb.set_trace()
        return []

    # All nodes cost just 1 to move to
    #move_cost = 0.2
    # visited node                                                                                                                                          
    visited =  [{},{}]
    enqueued = [{},{}]
    c = count()
    # frontier                                                                                                                                              
    # each queue is ( priority, counter (in case of degeneracy in priority), curnode, dist, parent)
    # save what index goes with each direction
    ind = {}
    ind['from_start_search'] = 0
    ind['from_goal_search'] = 1
    # Define weigh dictionary keywords for each direction
    ind[0] = 'dist_to_goal'
    ind[1] = 'dist_to_start'
    frontiers = [[],[]]
    heappush(frontiers[ind['from_start_search']],(start_to_goal_dist, next(c), node_s, 0, None))
    heappush(frontiers[ind['from_goal_search']],(start_to_goal_dist, next(c), node_g, 0, None))
    while frontiers[0] and frontiers[1]:
        current = [heappop(frontiers[0]),heappop(frontiers[1])]
        # stopping criterion: min(forward) + min(reverse) > shortest_path_in_graph                                                                          
        for direction_name in ['from_start_search','from_goal_search']:
            i = ind[direction_name]
            tr1,tr2, node,cost_to_here,parent = current[i]
            if node in visited[i]:
                continue
            else:
                visited[i][node] = parent
            del tr1,tr2
            if parent == None:
                last_move_direction = (2,2)  # All moves will get the same weight
            else:
                last_move_direction = (parent[0]-node[0],parent[1]-node[1])
            for neighbor,weights in graph[node]:
                if neighbor in visited[i]:
                    continue
                if (node[0]-neighbor[0],node[1]-neighbor[1]) == last_move_direction:
                    move_cost = 1
                else:
                    move_cost = 1*weight_multiplier
                current_cost = cost_to_here + move_cost
                distance = weights[ind[i]]
                if neighbor in enqueued[i]:
                    saved_cost, saved_move_cost = enqueued[i][neighbor]
                    if (saved_cost+saved_move_cost) <= current_cost:
                        continue
                
                enqueued[i][neighbor] = cost_to_here, move_cost
                heappush(frontiers[i], (current_cost+distance, next(c), neighbor, current_cost, node))

        intersection = set(visited[0]).intersection(set(visited[1]))
        if len(intersection)>0:
            intersecting_node = intersection.pop()
            finalpath = get_final_path(visited[0],node_s,intersecting_node,'start')
            path_ext = get_final_path(visited[1],node_g,intersecting_node,'goal')
            finalpath.extend(path_ext)
            if verbose:
                print("Final path found with length: {0}".format(len(finalpath)))
            return finalpath
    print("No path could be reached!")
    return []


def condense(path):
    '''
        Important routine. Goes through a newly created set of moves and 
        tries to eliminate redundant rows.
        If the same move is performed two timesteps in a row, they are combined
        into a single longer step
        This reduces the number of final steps in the movetable
        If both dt and dp for a step is 0, wait time is added after the previous move
        input:
            dts:    np.array  each value is the amount of change in theta
                              for that timestep
            dps:    np.array  each value is the amount of change in phi
                              for that timestep
        output:
            output_t: np.array   list of delta_theta moves after all merging is done
            output_p: np.array   list of delta_phi moves after all merging is done
            output_times: np.array   list of waittimes after each move after all merging is done
            
    '''
    # Intialize the arrays that will be output
    if len(path)>0:
        ts,ps = np.asarray(path).T
    else:
        return np.asarray([]),np.asarray([]),np.asarray([])
    dts = ts[1:]-ts[:-1]
    dps = ps[1:]-ps[:-1]
    output_t = [dts[0]]
    output_p = [dps[0]]
    output_times = [0.]
    current_column = 0
    # Loop through the given array of dthetas,dphis
    for i in range(1,dts.size):
        # If the change in theta and phi is the same as before,
        # We don't need a new step, just increase the time we perform
        # the previous step
        if dts[i]==dts[i-1] and dps[i]==dps[i-1]:
            output_t[current_column] += dts[i]
            output_p[current_column] += dps[i]
        # If we're not moving, we don't make a new move, we only add waittime
        # after the current move
        elif dts[i]==0 and dps[i]==0:
            #output_times[current_column] += 0.5
            continue
        # if none of the cases above, add a new move in the movetable
        # for the given dtheta, dphi, with no waittime 
        else:
            output_t.append(dts[i])
            output_p.append(dps[i])
            output_times.append(0.)
            current_column += 1
    return np.asarray(output_t),np.asarray(output_p),np.asarray(output_times)
        

def get_sampledpath_outlines(true_path_samps,thetaxys,phixys,tmin,pmin):
    xsamps,ysamps = [],[]
    for tsam,psam in true_path_samps:
        xsamp,ysamp = [],[]
        t_index = tsam-tmin
        p_index = psam-pmin
        theta_bods = thetaxys[t_index,:,:]
        phi_arms = phixys[t_index,p_index,:,:]          
        xsamp.extend(theta_bods[0,:])
        xsamp.extend(phi_arms[0,:])
        ysamp.extend(theta_bods[1,:])
        ysamp.extend(phi_arms[1,:])
        xsamps.append(xsamp)
        ysamps.append(ysamp)
    return xsamps, ysamps


def plot_result(path,boolgrid,xgrid,ygrid,xns,yns,heuristic,outline_xs=None,outline_ys=None):
    #nppath = np.asarray(path)
    #thetas = nppath[:,0]
    #phis = nppath[:,1]
    xs_path = [xgrid[i,j] for i,j in path]
    ys_path = [ygrid[i,j] for i,j in path]
    positioner_colors = ['k.','b.','c.','y.','g.','r.','m.']
        
    plt.figure()
    #plt.tight_layout()
    plt.pcolor(xgrid,ygrid,boolgrid.astype(int),alpha=0.1)
    plt.plot(xns,yns,'ks',markersize=2)
    plt.plot(xs_path[0],ys_path[0],'g^',markersize=6,markeredgecolor=None,markevery=4,markeredgewidth=0.001,alpha=1.0)
    plt.plot(xs_path[-1],ys_path[-1],'y*',markersize=6,markeredgecolor=None,markevery=4,markeredgewidth=0.001,alpha=1.0)
    if len(path)>2:
        plt.plot(xs_path[1:-1],ys_path[1:-1],'ro',markersize=4,markeredgecolor=None,markevery=4,markeredgewidth=0.001,alpha=0.4)
    if outline_xs is not None:
        for xpos,ypos,colo in zip(outline_xs,outline_ys,positioner_colors):
            plt.plot(xpos,ypos,colo,markersize=4,markeredgewidth=0.001,alpha=0.4)
    plt.title(heuristic)
    #plt.show()


def plot_comparison_weight_and_heur(paths,boolgrid,xgrid,ygrid,xns,yns,weights,heuristics,\
                unique_moves,outline_xs,outline_ys):
    #nppath = np.asarray(path)
    #thetas = nppath[:,0]
    #phis = nppath[:,1]
    #plt.tight_layout()
    colors = ['ro','b*','gs','c>','r*','bs','g>','co','rs','b>']
    positioner_colors = ['k.','b.','c.','y.','g.','r.','m.']
    if len(paths)>6:
        plotnum = 331
        figsize_tup = (3*6,3*6)
    elif len(paths)>4:
        plotnum = 231   #rows_cols_curplotnum
        figsize_tup = (3*6,3*6) # w,h
    elif len(paths)>2:
        plotnum = 221
        figsize_tup = (2*6,2*6)
    else:
        plotnum = 111
        figsize_tup = (6,6)
    plt.figure(figsize=figsize_tup)
    it = 0
    for heuristic in heuristics:
        for weight in weights:
            color = colors[it]
            path = paths[it]
            unique_move = unique_moves[it]
            xsamps = outline_xs[it]
            ysamps = outline_ys[it]
            plt.subplot(plotnum)
            plt.tight_layout()
            plt.pcolor(xgrid,ygrid,boolgrid.astype(int),alpha=0.1)
            if heuristic == 'manhattan':
                heuristic = 'mnhttn'
            if heuristic == 'euclidean':
                heuristic = 'eu'
            if heuristic == 'theta':
                heuristic = 'th'
            plt.plot(xns,yns,'ks',markersize=2)#4)
            xs_path = [xgrid[i,j] for i,j in path]
            ys_path = [ygrid[i,j] for i,j in path]
            plt.xticks([])
            plt.yticks([])
            plt.plot(xs_path[0],ys_path[0],'g^',markersize=6,markeredgecolor=None,markevery=4,markeredgewidth=0.001,alpha=1.0)
            plt.plot(xs_path[1:-1],ys_path[1:-1],color,markersize=4,markeredgecolor=None,markevery=4,markeredgewidth=0.001,alpha=0.4)
            plt.plot(xs_path[-1],ys_path[-1],'y*',markersize=6,markeredgecolor=None,markevery=4,markeredgewidth=0.001,alpha=1.0)
            for xpos,ypos,colo in zip(xsamps,ysamps,positioner_colors):
                plt.plot(xpos,ypos,colo,markersize=4,markeredgewidth=0.001,alpha=0.4)
            plt.title(heuristic+',w='+str(weight)+',n_mvs='+str(unique_move))
            plotnum += 1
            it += 1
    #plt.show()

    

def bidirectional_astar_pathfinding(curmodel, start, target, neighbors,thetaxys, phixys,\
                                    anticol_params, heuristics=[], weights=[]):

    
    if anticol_params is None:
        verbose = False
        plotting = True
        tolerance_xy = 0.4
        multitest = False
        #posoutlines = None
        heuristic = 'euclidean'
        weight = 1.2
    else:
        verbose = anticol_params.astar_verbose
        plotting = anticol_params.astar_plotting
        tolerance_xy = anticol_params.astar_tolerance_xy  
        multitest = anticol_params.multitest
        #posoutlines = anticol_params.posoutlines
        heuristic = anticol_params.astar_heuristic
        weight = anticol_params.astar_weight
        
    # Quantize the start and end targets to integers    
    true_goaltp = (int(target[0]),int(target[1]))
    true_starttp = (int(start[0]),int(start[1]))

    # Assign the max and min angles for theta and phi, quantized to integers
    post_minmax = curmodel.targetable_range_T
    posp_minpmax = curmodel.targetable_range_P
    obst_minmax,obsp_minmax = np.asarray(curmodel.trans.posTP_to_obsTP([post_minmax,posp_minpmax])).astype(np.int)

    tmin, tmax = obst_minmax[0], obst_minmax[1]
    pmin, pmax = obsp_minmax[0], obsp_minmax[1]
    #postmin,postmax = curmodel.targetable_range_T
    #pospmin,pospmax = curmodel.targetable_range_P
    #tpmin = curmodel.trans.posTP_to_obsTP([postmin,pospmin])
    #tpmax = curmodel.trans.posTP_to_obsTP([postmax,pospmax])
    ##phi_safe = curmodel.trans.posTP_to_obsTP([tmin+10,144])[1]
    #tmin,tmax = int(tpmin[0]),int(tpmax[0])
    #pmin,pmax = int(tpmin[1]),int(tpmax[1])

    # Create a grid of theta, phi values (optimized)
    # When turned into 1d arrays, we can loop over them in a single for loop
    # as though it were a double for loop
    true_pgrid,true_tgrid = np.meshgrid(np.arange(pmin,pmax+1),np.arange(tmin,tmax+1))
    
    assert true_pgrid.shape[0] == phixys.shape[0], "Theta and phi grids aren't the same dimensions as the input matrix of positions!" 
    assert true_pgrid.shape[1] == phixys.shape[1], "Theta and phi grids aren't the same dimensions as the input matrix of positions!" 

    # Create an equally shaped grid of positive integers. Essentially the indices of the above grid
    #index_pgrid,index_tgrid = np.meshgrid(np.arange(0,pmax-pmin+1),np.arange(0,tmax-tmin+1))

    # Get the obsXY values for all of the grid points
    #pos_tps = curmodel.trans.obsTP_to_posTP([true_tgrid.ravel(),true_pgrid.ravel()])
    #xvect,yvect = curmodel.trans.posTP_to_obsXY(pos_tps)
    #xgrid = np.asarray(xvect).reshape(true_tgrid.shape)
    #ygrid = np.asarray(yvect).reshape(true_tgrid.shape)
    xvect,yvect = curmodel.trans.obsTP_to_flatXY([true_tgrid.ravel(),true_pgrid.ravel()])
    xgrid = np.asarray(xvect).reshape(true_tgrid.shape)
    ygrid = np.asarray(yvect).reshape(true_tgrid.shape)
    # Determine where the goal and start indexes are in the grid
    index_goaltp = (true_goaltp[0]-tmin,true_goaltp[1]-pmin)
    index_starttp = (true_starttp[0]-tmin,true_starttp[1]-pmin)

    # Bring in the x and y values of the neighbors
    xns = neighbors['xns']
    yns = neighbors['yns']

    # Ensure that our assumption about goal and start locations match up with reality
    if true_tgrid[index_goaltp] != true_goaltp[0] or true_pgrid[index_goaltp] != true_goaltp[1]:
        print("Indices of the true goal and index grids didn't match up in bidirectional astar")
        pdb.set_trace()
    if true_tgrid[index_starttp] != true_starttp[0] or true_pgrid[index_starttp] != true_starttp[1]:
        print("Indices of the true start and index grids didn't match up in bidirectional astar")
        pdb.set_trace()

    # Create a boolean grid of allowable points. False = can't move to it
    boolgrid = build_bool_grid(xgrid,ygrid,xns,yns,thetaxys, phixys,tolerance_xy)
    
    # if verbose, print useful information
    if verbose:
        print("Trying to start from: {0} (tp)\t {1} (x,y)".format(true_starttp,(xgrid[index_starttp],ygrid[index_starttp])))
        print("and end up: {0} (tp)\t {1} (x,y)\n".format(true_goaltp,(xgrid[index_goaltp],ygrid[index_goaltp])))

    # Intialize the final outputs
    fin_path_t, fin_path_p, fin_path_time = None,None,None
            
    if plotting:
        unique_moves = []
        outline_xs = []
        outline_ys = []
    # Loop over the specified heuristics

    # Find the distances from every grid point to the starting point and goal point
    distances_tp_start = get_tp_distance(true_tgrid,true_pgrid,true_starttp,heuristic)
    distances_tp_goal = get_tp_distance(true_tgrid,true_pgrid,true_goaltp,heuristic)
   
    # Create a dictionary. The key is the points (i,j) location
    # The value for each key is the neighbor (in,jn) indices 
    # and the distance from the current (i,j) point to the start and goal
    graph = build_adjlist(boolgrid,distances_tp_start,distances_tp_goal)
    
    # Make sure that the start and goal aren't in the forbidden regions
    if index_starttp not in graph.keys() or index_goaltp not in graph.keys():
        multitest_results = {'heuristic':[heuristic],'weight':[weight],'pathlength_full':[np.nan],'pathlength_condensed':[np.nan],'found_path':[2]}
        print("It looks like the start or end point wasn't allowed in my astar bool map")
        # Now lets save the theta body locations for 4 points along the path for plotting purposes
        if plotting:
            true_path_samps = [true_starttp,true_goaltp]
            index_path_samps = [index_starttp,index_goaltp]
            outline_xs, outline_ys = get_sampledpath_outlines(true_path_samps,\
                                                              thetaxys,phixys,tmin,pmin)
    
            # Plot the neighboring positioners, the fiber movement throughout the move,
            # The boolean avoidance grid, and the positioner body for the start, 
            # 2 intermediate, and end moves
            plot_result(index_path_samps,boolgrid,xgrid,ygrid,xns,yns,'Non-Starter',outline_xs,outline_ys)
            plt.savefig('../figures/start_or_end_unaccessible_{}.png'.format(np.random.randint(low=0,high=2**31,size=1)),dpi=600)
            plt.close()
        #pdb.set_trace()
        return None,None,None, multitest_results

    # Run the bidirectional astar pathfinder (with multiplicative inertial parameter = weight)
    ind_path = find_path(graph, index_starttp, index_goaltp,distances_tp_goal[index_starttp], weight,verbose)
    
    # Assuming we found a path, clean it up and save it, otherwise return Nones
    if len(ind_path) == 0:
        multitest_results = {'heuristic':[heuristic],'weight':[weight],'pathlength_full':[np.nan],'pathlength_condensed':[np.nan],'found_path':[0]} 
        if verbose:
            print("No path found")       
        # Now lets save the theta body locations for 4 points along the path for plotting purposes
        if plotting:
            true_path_samps = [true_starttp,true_goaltp]
            index_path_samps = [index_starttp,index_goaltp]
            outline_xs, outline_ys = get_sampledpath_outlines(true_path_samps,\
                                                              thetaxys,phixys,tmin,pmin)
            # Plot the neighboring positioners, the fiber movement throughout the move,
            # The boolean avoidance grid, and the positioner body for the start, 
            # 2 intermediate, and end moves
            plot_result(index_path_samps,boolgrid,xgrid,ygrid,xns,yns,'Failed',outline_xs,outline_ys)
            
            plt.savefig('../../figures/nopath_weight-{0}_and_heuristics-th-euc_comp_{1}.png'.format(weight,str(time.time()).split('.')[0]),dpi=600)
            plt.close()
    else:
        true_path = [(i+tmin,j+pmin) for i,j in ind_path]
        fin_path_t, fin_path_p, fin_path_time = condense(true_path)
        if verbose:
            print("The reduced path using {0} and weight {1} is only: {2}__{3} moves long".format(heuristic, weight,len(ind_path),len(fin_path_t)))
          
        # Now lets save the theta body locations for 4 points along the path for plotting purposes
        if plotting:
            unique_moves.append(len(fin_path_t))
            npts = len(ind_path)
            nsamps = np.floor(npts/4).astype(int)
            samps = np.arange(4).astype(int)*nsamps
            samps[-1] = int(len(ind_path)-1)
            true_path_samps = [true_path[smp] for smp in samps]
            outline_xs, outline_ys = get_sampledpath_outlines(true_path_samps,\
                                                              thetaxys,phixys,tmin,pmin)
    
            # Plot the neighboring positioners, the fiber movement throughout the move,
            # The boolean avoidance grid, and the positioner body for the start, 
            # 2 intermediate, and end moves
            #plot_comparison_weight_and_heur([ind_path],boolgrid,xgrid,ygrid,xns,yns,\
            #                        [weight],[heuristic],unique_moves,outline_xs,outline_ys)
            plot_result(ind_path,boolgrid,xgrid,ygrid,xns,yns,\
                                    heuristic,outline_xs,outline_ys)
            plt.savefig('../figures/weight-{0}_and_heuristics-th-euc_comp_{1}.png'.format(weight,str(time.time()).split('.')[0]),dpi=600)
            plt.close()
    
        # If testing out multiple heuristics and or weights, loop over them.
        # They aren't plotted but their parameters are stored
        multitest_results = {'heuristic':[heuristic],'weight':[weight],'pathlength_full':[len(ind_path)],'pathlength_condensed':[len(fin_path_t)],'found_path':[1]}
        
    if multitest:
        for test_heuristic in heuristics:  
            # Find the distances from every grid point to the starting point and goal point
            distances_tp_start = get_tp_distance(true_tgrid,true_pgrid,true_starttp,test_heuristic)
            distances_tp_goal = get_tp_distance(true_tgrid,true_pgrid,true_goaltp,test_heuristic)
            # Create a dictionary. The key is the points (i,j) location
            # The value for each key is the neighbor (in,jn) indices 
            # and the distance from the current (i,j) point to the start and goal
            graph = build_adjlist(boolgrid,distances_tp_start,distances_tp_goal)
            for test_weight in weights:
                if test_heuristic == heuristic and test_weight == weight:
                    continue
                multitest_results['heuristic'].append(test_heuristic)
                multitest_results['weight'].append(test_weight)
                test_ind_path = find_path(graph, index_starttp, index_goaltp,distances_tp_goal[index_starttp], test_weight,verbose)
                # Assuming we found a path, clean it up and save it
                if len(test_ind_path) == 0:
                    multitest_results['pathlength_full'].append(np.nan)
                    multitest_results['pathlength_condensed'].append(np.nan)
                    multitest_results['found_path'].append(0)
                else:
                    true_test_path = [(i+tmin,j+pmin) for i,j in test_ind_path]
                    condensed_path_t, condensed_path_p, condensed_path_time = condense(true_test_path)
                    multitest_results['pathlength_full'].append(len(test_ind_path))
                    multitest_results['pathlength_condensed'].append(len(condensed_path_t))
                    multitest_results['found_path'].append(1)

    if len(ind_path) == 0:
        return None, None, None, multitest_results    
    else:
        return fin_path_t, fin_path_p, fin_path_time, multitest_results