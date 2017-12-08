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

#heuristic = 'euclidean'#'phi'



###########################
# Actual Code
###########################
def get_tp_distance(tgrid,pgrid,target,heuristic='phi'):
    if heuristic.lower() == 'phi':
        return pgrid-target[1]+np.max(pgrid)
    elif heuristic.lower() == 'theta':
        return tgrid-target[0]+np.max(tgrid)
    elif heuristic.lower() == 'euclidean':
        return np.hypot(tgrid.ravel()-target[0],\
                        pgrid.ravel()-target[1]).reshape(tgrid.shape) \
                        + np.hypot(np.max(tgrid),np.max(pgrid))
    elif heuristic.lower() == 'manhattan':
        return (tgrid + pgrid) - (target[0] + target[1]) + np.max(tgrid) + np.max(pgrid)
    else:
        print('Heuristic did not match any available methods in get_tp_distance')
        return np.zeros(tgrid.shape)



def build_bool_grid(xs,ys,xns,yns,xnts,ynts,tolerance):
    #rows,cols = xs.shape
    #dx = np.mean(xs[rows//2,1:]-xs[rows//2,:-1])
    #dy = np.mean(ys[1:,cols//2]-ys[:-1,cols//2])
    #dist = mean(dx,dy)
    all_xns = np.concatenate([xns,xnts])
    all_yns = np.concatenate([yns,ynts])
    bool_map = np.zeros(xs.size).astype(bool)
    xravel = xs.ravel()
    yravel = ys.ravel()
    for x,y in zip(all_xns,all_yns): 
        bool_temp = ( ( np.abs(xravel-x) < tolerance) & ( np.abs(yravel-y) < tolerance ) )
        #pdb.set_trace()
        bool_map = ( bool_map | bool_temp )
    return bool_map.reshape(xs.shape)



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
            output_times[current_column] += 0.5
        # if none of the cases above, add a new move in the movetable
        # for the given dtheta, dphi, with no waittime 
        else:
            output_t.append(dts[i])
            output_p.append(dps[i])
            output_times.append(0.)
            current_column += 1
    return np.asarray(output_t),np.asarray(output_p),np.asarray(output_times)
        


def plot_result(path,boolgrid,xgrid,ygrid,xns,yns,heuristic):
    #nppath = np.asarray(path)
    #thetas = nppath[:,0]
    #phis = nppath[:,1]
    xs_path = [xgrid[i,j] for i,j in path]
    ys_path = [ygrid[i,j] for i,j in path]
    plt.figure()
    plt.plot(xns,yns,'k^',markersize=12)
    plt.plot(xs_path,ys_path,'ro',markersize=12)
    plt.title(heuristic)
    #plt.show()

def plot_comparison_heuristics(paths,boolgrid,xgrid,ygrid,xns,yns,weight,heuristics,unique_moves):
    #nppath = np.asarray(path)
    #thetas = nppath[:,0]
    #phis = nppath[:,1]
    plt.figure()
    colors = ['ro','b*','gs','c>']
    if len(heuristics)>2:
        plotnum = 221
    else:
        plotnum = 121
    for path,heuristic,color,unique_move in zip(paths,heuristics,colors,unique_moves):
        plt.subplot(plotnum)
        if heuristic == 'manhattan':
            heuristic = 'mnhttn'
        if heuristic == 'euclidean':
            heuristic = 'euclid'
        plt.plot(xns,yns,'k^',markersize=12)
        xs_path = [xgrid[i,j] for i,j in path]
        ys_path = [ygrid[i,j] for i,j in path]
        plt.plot(xs_path,ys_path,color,markersize=8,markeredgecolor=None,markevery=4,markeredgewidth=0.001,alpha=0.4)
        plt.title(heuristic+', w='+str(weight)+', uniq_mvs='+str(unique_move))
        plotnum +=1
    #plt.show()


def plot_comparison_weight_and_heur(paths,boolgrid,xgrid,ygrid,xns,yns,weights,heuristics,\
                unique_moves,outline_xs,outline_ys):
    #nppath = np.asarray(path)
    #thetas = nppath[:,0]
    #phis = nppath[:,1]
    plt.figure()
    #plt.tight_layout()
    colors = ['ro','b*','gs','c>','r*','bs','g>','co','rs','b>']
    if len(paths)>6:
        plotnum = 331
    elif len(paths)>4:
        plotnum = 231
    elif len(paths)>2:
        plotnum = 221
    else:
        print("I can't plot all of those. Only plotting first 2")
        plotnum = 121
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
            if heuristic == 'manhattan':
                heuristic = 'mnhttn'
            if heuristic == 'euclidean':
                heuristic = 'eu'
            if heuristic == 'theta':
                heuristic = 'th'
            plt.plot(xns,yns,'k^',markersize=6)
            xs_path = [xgrid[i,j] for i,j in path]
            ys_path = [ygrid[i,j] for i,j in path]
            plt.xticks([])
            plt.yticks([])
            plt.plot(xs_path,ys_path,color,markersize=6,markeredgecolor=None,markevery=4,markeredgewidth=0.001,alpha=0.4)
            plt.plot(xsamps,ysamps,color[0]+'.',markersize=6,markeredgewidth=0.001,alpha=0.2)
            plt.title(heuristic+',w='+str(weight)+',n_mvs='+str(unique_move))
            plotnum += 1
            it += 1
    #plt.show()



def pliers(curmodel,start,target,neighbors,dp_direction,posoutlines):
    xns = neighbors['xns']#np.concatenate((neighbors['xns'],neighbors['theta_body_xns']))
    yns = neighbors['yns']#np.concatenate((neighbors['yns'],neighbors['theta_body_yns']))
    tmin,tmax = curmodel.targetable_range_T
    pmin,pmax = curmodel.targetable_range_P
    negtgridT, negpgridT = np.meshgrid(np.arange(tmin,tmax+1),np.arange(pmin,pmax+1))
    negtgrid, negpgrid = negtgridT.T, negpgridT.T
    xvect,yvect = curmodel.trans.obsTP_to_flatXY([negtgrid.ravel(),negpgrid.ravel()])
    xgrid = np.asarray(xvect).reshape(negtgrid.shape)
    ygrid = np.asarray(yvect).reshape(negtgrid.shape)
    goaltp = (int(target[0]),int(target[1]))
    starttp = (int(start[0]),int(start[1]))
    return xns,yns,goaltp,negtgrid,negpgrid,xgrid,ygrid,starttp,posoutlines


    
def load_data(vers):
    # Load the pre generated data
    fulldict = pkl.load(open('fullgrid_20poss_{0}.pkl'.format(vers),'rb'))
    print("Using file {0}".format(vers))        
    # Unpack data
    xgrid,ygrid = fulldict['xs'].T,fulldict['ys'].T
    negtgrid,negpgrid = fulldict['thetagrid'].T,fulldict['phigrid'].T
    goaltp = (int(fulldict['targtp'][0]),int(fulldict['targtp'][1]))
    xns,yns = fulldict['xns'],fulldict['yns']
    return xns,yns,goaltp,negtgrid,negpgrid,xgrid,ygrid
    
    
    
def bidirectional_astar_pathfinding(xns,yns,goaltp,negtgrid,negpgrid,xgrid,ygrid,starttp=None,posoutlines=None):
    #distances_xy = np.hypot(xgrid-goalxy[0],ygrid-goalxy[1])
    #direction = np.sign(goaltp[1]-starttp[1])
    # Adjust for angle offsets
    verbose = False
    tolerance_xy = 0.6
    theta_offset = np.min(negtgrid)
    phi_offset = np.min(negpgrid)
    tgrid = negtgrid-theta_offset
    pgrid = negpgrid-phi_offset 
    goaltp_offset = (int(goaltp[0]-theta_offset),int(goaltp[1]-phi_offset))
    heuristics = ['theta','euclidean'] # 'phi','manhattan',
    omni_weights = [[1,1.2,1.4],[1.6,1.8,2.0]]#,4]
    if starttp == None:
        starttp_offset = (int(np.random.randint(np.min(tgrid[:,0]),np.max(tgrid[:,0]),1)),\
                   int(np.random.randint(np.min(pgrid[0,:]),np.max(pgrid[0,:]),1)))
        starttp = (int(starttp_offset[0]+theta_offset),int(starttp_offset[1]+phi_offset))
    else:
        starttp_offset = (int(starttp[0]-theta_offset),int(starttp[1]-phi_offset))
    fin_path_t, fin_path_p, fin_path_time = None,None,None
    if verbose:
        print("Trying to start from: {0} (tp)\t\t {1} (x,y)".format(starttp,(xgrid[starttp_offset],ygrid[starttp_offset])))
        print("and end up: {0} (tp)\t\t {1} (x,y)".format(goaltp,(xgrid[goaltp_offset],ygrid[goaltp_offset])))
    for weights in omni_weights:
        paths = []
        unique_moves = []
        for heuristic in heuristics:
            distances_tp_start = get_tp_distance(tgrid,pgrid,starttp_offset,heuristic)
            distances_tp_goal = get_tp_distance(tgrid,pgrid,goaltp_offset,heuristic)
            boolgrid = build_bool_grid(xgrid,ygrid,xns,yns,[],[],tolerance_xy)
            graph = build_adjlist(boolgrid,distances_tp_start,distances_tp_goal)
            if starttp_offset not in graph.keys():
                break
            if goaltp_offset not in graph.keys():
                break
            for weight in weights:
                if verbose:
                    print('\n')
                path = find_path(graph, starttp_offset, goaltp_offset,distances_tp_goal[starttp_offset], weight,verbose)
                if len(path) == 0:
                    continue
                true_path = [(i+theta_offset,j+phi_offset) for i,j in path]
                condensed_path_t, condensed_path_p, condensed_path_time = condense(true_path)
                if verbose:
                    print("The reduced path using {0} and weight {1} is only: {2} moves long".format(heuristic, weight,len(condensed_path_t)))
                paths.append(path)
                unique_moves.append(len(condensed_path_t))
                if heuristic == 'euclidean' and weight == 1.2:
                    fin_path_t, fin_path_p, fin_path_time = condensed_path_t, condensed_path_p, condensed_path_time
                #plot_result(path,boolgrid,xgrid,ygrid,xns,yns,heuristic)
            #plot_comparison_heuristics(paths,boolgrid,xgrid,ygrid,xns,yns,weight,heuristics,unique_moves)
        if len(paths)>0:
            base = ''
            for k in weights:
                base += '-'+str(k)
            outline_xs = []
            outline_ys = []
            for path in paths:
                npts = len(path)
                nsamps = np.floor(npts/4).astype(int)
                samps = np.arange(4).astype(int)*nsamps
                path_samps = [path[smp] for smp in samps]
                xsamps = []
                ysamps = []
                for psamp in path_samps:
                    tsam,psam = negtgrid[psamp],negpgrid[psamp]
                    xsam,ysam = xgrid[0,-1],ygrid[0,-1]
                    theta_bods = posoutlines.central_body_outline([tsam,psam],[xsam,ysam])
                    phi_arms = posoutlines.phi_arm_outline([tsam,psam],3.0,[xsam,ysam])            
                    xsamps.extend(theta_bods[0,:])
                    xsamps.extend(phi_arms[0,:])
                    ysamps.extend(theta_bods[1,:])
                    ysamps.extend(phi_arms[1,:])
                outline_xs.append(xsamps)
                outline_ys.append(ysamps)
            plot_comparison_weight_and_heur(paths,boolgrid,xgrid,ygrid,xns,yns,\
                                    weights,heuristics,unique_moves,outline_xs,outline_ys)
            plt.savefig('../figures/weight{0}_and_heuristics-th-euc_comp_{1}.png'.format(base,str(time.time()).split('.')[0]),dpi=600)
            pkl.dump({'paths':true_path,'nunique_moves':unique_moves,'condensed_th-ph-t':[condensed_path_t, condensed_path_p, condensed_path_time],'weights':weights,'heuristics':heuristics},open('../outputs/weight{0}_and_heuristics-th-euc_comp_{1}.pkl'.format(base,str(time.time()).split('.')[0]),'wb'))
            plt.close()
    
    return fin_path_t, fin_path_p, fin_path_time




class PosOutlines:
    def __init__(self,collider,spacing=0.4):
        self.spacing = 0.4
        self.thetapoints = self._highres(collider.keepout_T.points.copy())
        self.phipoints = self._highres(collider.keepout_P.points.copy())
        self.ferrulepoints = self._highres(collider.ferrule_poly.points.copy())
        possible_petal_pts = collider.keepout_PTL.points.copy()
        petaly = possible_petal_pts[1,:]
        actual_petal = np.where((petaly > -1.) & (petaly < 249.))[0]
        true_petal_pts = possible_petal_pts[:,actual_petal]
        self.petalpoints = self._highres(true_petal_pts)
        self._rotmat2D_deg = collider.keepout_T._rotmat2D_deg
   
    def phi_arm_outline(self, obsTP, R1, xyoff):
        """Rotates and translates the phi arm to position defined by the positioner's
        xy0 and the argued obsTP (theta,phi) angles.
        """
        polypts = self.phipoints.copy()
        polypts = self._rotate(polypts,obsTP[1])
        polypts = self._translate(polypts,R1, 0)
        polypts = self._rotate(polypts,obsTP[0])
        polypts = self._translate(polypts,xyoff[0], xyoff[1])
        return polypts
    
    def central_body_outline(self, obsTP, xyoff):
        """Rotates and translates the central body of positioner identified by idx
        to it's xy0 and the argued obsT theta angle.
        """
        polypts = self.thetapoints.copy()
        polypts = self._rotate(polypts,obsTP[0])
        polypts = self._translate(polypts,xyoff[0], xyoff[1])
        return polypts
    
    def ferrule_outline(self, obsTP, R1, R2, xyoff):
        """Rotates and translates the ferrule to position defined by the positioner's
        xy0 and the argued obsTP (theta,phi) angles.
        """
        polypts = self.ferrulepoints.copy()
        polypts = self._translate(polypts,R2, 0)
        polypts = self._rotate(polypts,obsTP[1])
        polypts = self._translate(polypts,R1,0)
        polypts = self._rotate(polypts,obsTP[0])
        polypts = self._translate(polypts,xyoff[0], xyoff[1])
        return polypts

    def petal_outline(self,positioner_x,positioner_y, radius):
        """Returns the petal outline
        """
        dx = self.petalpoints[0,:]-positioner_x
        dy = self.petalpoints[1,:]-positioner_y
        nearby = np.where(np.hypot(dx,dy) < radius)[0]
        return self.petalpoints[:,nearby]
 
    def _highres(self,endpts):
        closed_endpts = np.hstack([endpts,endpts[:,0].reshape(2,1)])
        diffs = np.diff(closed_endpts,axis=1)
        dists = np.hypot(diffs[0,:],diffs[1,:])
        #maxdiffs = diffs.max(axis=0)
        npts = np.ceil(dists/self.spacing).astype(np.int).clip(2,1e4)
        xs,ys = [],[]
        for i in np.arange(0,closed_endpts.shape[1]-1):
            xs.extend(np.linspace(closed_endpts[0,i],closed_endpts[0,i+1],npts[i]))
            ys.extend(np.linspace(closed_endpts[1,i],closed_endpts[1,i+1],npts[i]))
        return np.asarray([xs,ys])
       
    def _rotate(self, points, angle):
        """Returns a copy of the polygon object, with points rotated by angle (unit degrees)."""
        return np.dot(self._rotmat2D_deg(angle), points)

    def _translate(self, points, x, y):
        """Returns a copy of the polygon object, with points translated by distance (x,y)."""
        return points + np.array([[x],[y]])



if __name__ == '__main__':
    xns,yns,goaltp,negtgrid,negpgrid,xgrid,ygrid = load_data(1)
    cth,cp,cti = bidirectional_astar_pathfinding(xns,yns,goaltp,negtgrid,negpgrid,xgrid,ygrid,starttp=None)