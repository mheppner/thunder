# tuning <master> <dataFile> <modelFile> <outputDir> <mode> <opts>

import sys
import os
from numpy import *
from pyspark import SparkContext
from thunder.util.dataio import *
from thunder.regression.util import *
from thunder.factorization.util import *

argsIn = sys.argv[1:]
if len(argsIn) < 6:
  print >> sys.stderr, \
  "(regress) usage: regress <master> <inputFile_Y> <inputFile_X> <outputFile> <regressMode> <outputMode> <opts>"
  exit(-1)

# parse inputs
sc = SparkContext(argsIn[0], "regress")
dataFile = str(argsIn[1])
modelFile = str(argsIn[2])
outputDir = str(argsIn[3]) + "-regress"
regressionMode = str(argsIn[4])
tuningMode = str(argsIn[5])
if not os.path.exists(outputDir) :
	os.makedirs(outputDir)

# parse data
data = sc.textFile(dataFile).map(lambda x : parse(x,"dff")).cache()

# create models
model1 = regressionModel(modelFile,regressionMode)
model2 = tuningModel(modelFile,tuningMode)

# do regression
betas = data.map(lambda y : regressionFit(y,model1)).cache()

# get statistics
stats = betas.map(lambda x : x[2])
saveout(stats,outputDir,"stats","matlab")

# do PCA on first fit component
comps,latent,scores = svd1(betas.map(lambda x : x[0]),2)
saveout(comps,outputDir,"comps","matlab")
saveout(latent,outputDir,"latent","matlab")
saveout(scores,outputDir,"scores","matlab")

# calculate tuning curves on second fit component
params = betas.map(lambda x : tuningFit(x[1],model2))
saveout(params,outputDir,"params","matlab")

# process output with a parametric tuning curves
# if outputMode == 'tuning' :
# 	B = Y.map(lambda y : getRegression(y,model)).cache()
# 	p = B.map(lambda b : float16(getTuning(b[0],model))).collect()
# 	savemat(outputFile+"/"+"p.mat",mdict={'p':p},oned_as='column',do_compression='true')
# 	# get population tuning curves
# 	vals = linspace(min(model.s),max(model.s),6)
# 	means = zeros((len(vals)-1,len(model.s)))
# 	sds = zeros((len(vals)-1,len(model.s)))
# 	for iv in range(0,len(vals)-1) :
# 		subset = B.filter(lambda b : (b[1] > 0.005) & inRange(getTuning(b[0],model)[0],vals[iv],vals[iv+1]))
# 		n = subset.count()
# 		means[iv,:] = subset.map(lambda b : b[0]).reduce(lambda x,y : x + y) / n
# 		sds[iv,:] = subset.map(lambda b : (b[0] - means[iv,:])**2).reduce(lambda x,y : x + y) / (n - 1)
# 		savemat(outputFile+"/"+"means.mat",mdict={'means':means},do_compression='true')
# 		savemat(outputFile+"/"+"sds.mat",mdict={'sds':sds},do_compression='true')

# def inRange(val,rng1,rng2) :
# 	if (val > rng1) & (val < rng2):
# 		return True
# 	else:
# 		return False