import networkx as nx
import numpy as np
import nltk
import math
from nltk.tokenize import sent_tokenize 
from nltk.tokenize import word_tokenize
from nltk.tokenize.punkt import PunktSentenceTokenizer
from sklearn.feature_extraction.text import TfidfTransformer, CountVectorizer
  
from nltk.corpus import stopwords
from nltk.stem.lancaster import LancasterStemmer
import re
import operator

import requests
import goose

proxies = {
  "http": "http://10.3.100.207:8080",
  "https": "http://10.3.100.207:8080",
}

class ArticleExtractor():

	@staticmethod
	def filter_unicode(str):
		str = str.encode('ascii', 'ignore')
		str = str.replace("\n", " ")
		return str

	@staticmethod
	def parse(url):
		page = requests.get(url, proxies = proxies)
		g = goose.Goose()
		#article = g.extract(url=url)
		article = g.extract(raw_html = page.text)
		items = {}
		items['headline'] = article.title
		items['text'] = ArticleExtractor.filter_unicode(article.cleaned_text)
		return items

class CommunitySummarizer():
	@staticmethod
	def textrank(sentences):
		# sentences = sent_tokenize(document) 
		bow_matrix = CountVectorizer().fit_transform(sentences)
		normalized = TfidfTransformer().fit_transform(bow_matrix)
		similarity_graph = normalized * normalized.T
		nx_graph = nx.from_scipy_sparse_matrix(similarity_graph)
		scores = nx.pagerank(nx_graph)
		# print scores[0]
		scores = [scores[i] for i in range(len(scores))]
		if(not(max(scores)==min(scores))):
			mi = min(scores)
			scores = [i- mi for i in (scores)]
		ma = max(scores)
		scores = [i/ma for i in (scores)]
		  # reverse=True)
		# print sortedSencence[0][1]
		# print scores
	 	return scores

	@staticmethod
	def summarize(document):
		sentences = sent_tokenize(document) 
		bow_matrix = CountVectorizer(stop_words = 'english').fit_transform(sentences)
		normalized = TfidfTransformer().fit_transform(bow_matrix)
		similarity_graph = normalized * normalized.T
		nx_graph = nx.from_scipy_sparse_matrix(similarity_graph)
		sub_graphs = []
	    #n gives the number of sub graphs
		edge_wts = nx_graph.edges(data=True)
		edge_wts.sort(key=lambda (a, b, dct): dct['weight'],reverse=True)
		k = 10 #number of sentence in summary
		G = nx.Graph()
		for i in nx_graph.nodes():
			G.add_node(i)
		for u,v,d in edge_wts:
			G.add_edge(u,v,d)
			sub_graphs = nx.connected_component_subgraphs(G)
			# print sub_graphs
			n = len(sub_graphs)
			if n == k:	break
		inSummary = [0 for i in range(len(sentences))]

		n = len(sub_graphs)
		for i in range(n):
			sen = [sentences[j] for j in (sub_graphs[i].nodes())]
			arr = [j for j in (sub_graphs[i].nodes())]
			scores = CommunitySummarizer.textrank(sen)
			# print (scores)
			# print (arr)
			for j in range(len(arr)):
				inSummary[arr[j]] = scores[j];
		# print inSummary
		summ = [sentences[i] for i in range(len(inSummary)) if inSummary[i]>=1]
		# print len(summ)
		return summ

class KeyPhraseSummarizer():

	NUM_NP = 10
	K = 5
	stopword_list = stopwords.words('english')
	
	@staticmethod
	def preprocess(body):
		sent_tokenizer = nltk.data.load('tokenizers/punkt/english.pickle')

		body = sent_tokenizer.tokenize(body)
		body = [word_tokenize(sent) for sent in body]
		body = [nltk.pos_tag(sent) for sent in body]
		
		return body

	@staticmethod
	def acceptable_phrase(phrase):
		l = [word for word in phrase.split() if word not in KeyPhraseSummarizer.stopword_list and len(word) > 3]
		return len(l) > 0

	@staticmethod
	def cleaned_phrase(phrase):
		cleaned = ""
		for word in phrase.split():
			if KeyPhraseSummarizer.acceptable_phrase(word):
				cleaned = word + " "
		cleaned = cleaned.strip()
		return cleaned
	
	@staticmethod
	def get_score(keyphrases, freq_phrases, freq_words):
		score = 0
		for phrase in freq_phrases.items():
			for keyphrase in keyphrases:
				if phrase[0] == keyphrase[0]:
					score += keyphrase[1] * math.sqrt(phrase[1])
					break
					
		for word in freq_words.items():
			for keyphrase in keyphrases:
				if word[0] == keyphrase[0]:
					score += keyphrase[1] * math.sqrt(word[1])
					break
		return score

	@staticmethod
	def leaves_NP(tree):
		for subtree in tree.subtrees(filter = lambda t: t.label()=='NP'):
			yield subtree.leaves()
		
	@staticmethod
	def summarize(body):

		body_pos = KeyPhraseSummarizer.preprocess(body)
			
		# grammar = "NP: {<DT>?<JJ>*<NN>}"
		grammar = r"""
		NBAR:
		{<NN.*|JJ>*<NN.*>}  # Nouns and Adjectives, terminated with Nouns
		
		NP:
		{<DT>?<JJ>*<NN>}
		{<NBAR>}
		{<NBAR><IN><NBAR>}  # Above, connected with in/of/etc...
		"""
		chunker = nltk.RegexpParser(grammar)
		trees = [chunker.parse(sent) for sent in body_pos]
		
		NP = {}
		cnt = 0
		for tree in trees:
			for leaf_NP in KeyPhraseSummarizer.leaves_NP(tree):
				
				phrase = ""
				for word in leaf_NP:
					phrase += str(word[0]).lower() + " "
				phrase = phrase.strip()
				phrase = KeyPhraseSummarizer.cleaned_phrase(phrase)
				
				if phrase in NP:
					NP[phrase] += 1
				elif KeyPhraseSummarizer.acceptable_phrase(phrase):
					NP[phrase] = 1
				
				if len(phrase.split()) > 1:
					for word in phrase.split():
						if word in NP:
							NP[word] += 1.0 / len(phrase.split())
						elif KeyPhraseSummarizer.acceptable_phrase(word):
							NP[word] = 1.0 / len(phrase.split())
							
		keyphrases = sorted(NP.items(), key=operator.itemgetter(1), reverse = True)[0 : KeyPhraseSummarizer.NUM_NP+1]
		keyphrases = [(phrase[0], float(phrase[1]) / len(NP)) for phrase in keyphrases]

		scores_dict = {}
		sent_score = [0.0 for x in trees]
		for i, tree in enumerate(trees):
			score = 0
			freq_phrases = {}
			freq_words = {}
			for leaf_NP in KeyPhraseSummarizer.leaves_NP(tree):
				phrase = ""
				for word in leaf_NP:
					phrase += str(word[0]).lower() + " "
				phrase = phrase.strip()
				phrase = KeyPhraseSummarizer.cleaned_phrase(phrase)
				
				if phrase in freq_phrases:
					freq_phrases[phrase] += 1
				elif KeyPhraseSummarizer.acceptable_phrase(phrase):
					freq_phrases[phrase] = 1
					
				if len(phrase.split()) > 1:
					for word in phrase.split():
						if word in freq_words:
							freq_words[word] += 1
						elif KeyPhraseSummarizer.acceptable_phrase(word):
							freq_words[word] = 1
			score = KeyPhraseSummarizer.get_score(keyphrases, freq_phrases, freq_words)
			scores_dict[i] = score
			sent_score[i] = score
			
		if len(body_pos)/3>4:
			KeyPhraseSummarizer.K = 4
		else:
			KeyPhraseSummarizer.K = len(body_pos)/3
			
		scores = sorted(scores_dict.items(), key=operator.itemgetter(1), reverse = True)[0 : KeyPhraseSummarizer.K + 1]
			
		scores = sorted(scores, key = operator.itemgetter(0))
			
		sent_tokenizer = nltk.data.load('tokenizers/punkt/english.pickle')
		body_sent = sent_tokenizer.tokenize(body)
		summary = []
		if scores[0][0] != 0:
			summary.append((body_sent[0], 0, scores_dict[0]))
		for score in scores:
			summary.append((body_sent[score[0]], score[0], score[1]))
		#return summary
		return [sent[0] for sent in summary]
			

class LuhnSummarizer():

	fraction_of_lines = 0.33

	@staticmethod
	def summarize(document):

		stop_words_list = stopwords.words('english')
		doc_word_list = re.split(r'[,;.\s]\s*',document)
		sentences = sent_tokenize(document)
		st = LancasterStemmer()
		
		if len(sentences)/3>10:
			K = 10
		else:
			K = len(sentences)/3
		K = K+1
		
		word_frequency_dict = dict()
		for sent in sentences:
			sent_word_list = re.split(r'[,;.\s]\s*',sent)
			for (i,word) in enumerate(sent_word_list):
				if len(word)==0 or word.lower() in stop_words_list:
					continue
				stem_word = st.stem(word)
				if stem_word in word_frequency_dict.keys():
					word_frequency_dict[stem_word] = word_frequency_dict[stem_word]+1
				else:
					word_frequency_dict[stem_word] = 1
				if i!=0 and word[0].isupper()==True:
					word_frequency_dict[stem_word] = word_frequency_dict[stem_word] + 0.2 #Adhoc weight


		sentence_scores = [[0.0,x] for x in xrange(len(sentences))]
		scores = [0.0 for x in xrange(len(sentences))]
		n_sentences = len(sentences)

		for (i,sent) in enumerate(sentences):
			sent_word_list = re.split(r'[,;.\s]\s*',sent)
			if len(sent_word_list) <= 5: #Eliminate sentences of less than 5 words
				continue
			significance_vector = []
			for word in sent_word_list:
				if len(word)==0:
					continue
				if word.lower() in stop_words_list:
					significance_vector.append(0)
					continue
				stem_word = st.stem(word)
				if stem_word in word_frequency_dict.keys():
					stem_word_freq = word_frequency_dict[stem_word]
				else:
					stem_word_freq = 0
				if(stem_word_freq>1):
					significance_vector.append(stem_word_freq)
				else:
					significance_vector.append(0)
			cluster_score = []
			blankCount = 0
			clusterCount = 0
			clusterSum = 0
			for idx in xrange(len(significance_vector)):
				clusterSum  = clusterSum+significance_vector[idx]
				clusterCount = clusterCount+1
				if significance_vector[idx]==0:
					blankCount = blankCount+1
				if(blankCount>4):
					cluster_score.append(clusterSum/(clusterCount**2))
					blankCount=0
					clusterCount=0
					clusterSum=0
			if clusterCount>0:
				cluster_score.append(clusterSum/(clusterCount**2))
			sentence_scores[i][0] = 1.0/min(i+1,n_sentences-i) + max(cluster_score)
			scores[i] = sentence_scores[i][0]

		#Sorted_list is a list of two-member lists of (sentence score, index) sorted by score
		sorted_list = sorted(sentence_scores,reverse=True)
		topK = []

		#Can swap out number_of_lines for fraction of article lines here
		for i in xrange(K):
			#topK is a list of lists of (sentence index, score) with top k scores
			topK.append([sorted_list[i][1],sorted_list[i][0]])
		
		#Final_sent_list is topK sorted by sentence index (sentences in order of appearance)
		final_sent_list = sorted(topK)

		summary = []
		for sent_score in final_sent_list:
			summary.append(sentences[sent_score[0]])

		return summary


class PageRankSummarizer():

	numberOfLines = 5
	fractionOfLines = 0.3
	takeFraction = True 

	@staticmethod
	def textrank(document):
		sentences = sent_tokenize(document) 
		bow_matrix = CountVectorizer().fit_transform(sentences)
		normalized = TfidfTransformer().fit_transform(bow_matrix)
		similarity_graph = normalized * normalized.T
		nx_graph = nx.from_scipy_sparse_matrix(similarity_graph)
		scores = nx.pagerank(nx_graph)
		return  sorted(((scores[i],i,s) for i,s in enumerate(sentences)),
		  reverse=True)

	@staticmethod
	def getScore(item):
		return item[0]	

	@staticmethod
	def getTextOrderKey(item):
		return item[1]

	@staticmethod
	def getText(item):
		return item[2]		

	@staticmethod
	def summarize(document):
		topK=0
		sortedSencence = PageRankSummarizer.textrank(document)

		if PageRankSummarizer.takeFraction:
			topK = int(math.ceil(PageRankSummarizer.fractionOfLines*len(sortedSencence)))
		else:
			if(PageRankSummarizer.numberOfLines>len(sortedSencence)):
				topK=len(sortedSencence)
			else:
				topK=PageRankSummarizer.numberOfLines
		# print topK
		del(sortedSencence[topK:])
		values =  sorted(sortedSencence, key=PageRankSummarizer.getTextOrderKey)
		result = [ PageRankSummarizer.getText(sentence) for sentence in values]
		del values
		return result

