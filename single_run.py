"""Example running MemN2N on a single bAbI task.
Download tasks from facebook.ai/babi """
from __future__ import absolute_import
from __future__ import print_function

from data_utils import load_task, vectorize_data
from sklearn import cross_validation, metrics
from memn2n import MemN2N
from itertools import chain
from six.moves import range, reduce

import tensorflow as tf
import numpy as np

tf.flags.DEFINE_float("learning_rate", 0.01, "Learning rate for SGD.")
tf.flags.DEFINE_float("anneal_rate", 10, "Number of epochs between halving the learnign rate.")
tf.flags.DEFINE_float("anneal_stop_epoch", 100, "Epoch number to end annealed lr schedule.")
tf.flags.DEFINE_float("max_grad_norm", 40.0, "Clip gradients to this norm.")
tf.flags.DEFINE_integer("evaluation_interval", 10, "Evaluate and print results every x epochs")
tf.flags.DEFINE_integer("batch_size", 32, "Batch size for training.")
tf.flags.DEFINE_integer("hops", 3, "Number of hops in the Memory Network.")
tf.flags.DEFINE_integer("epochs", 250, "Number of epochs to train for.")
tf.flags.DEFINE_integer("embedding_size", 30, "Embedding size for embedding matrices.")
tf.flags.DEFINE_integer("memory_size", 50, "Maximum size of memory.")
tf.flags.DEFINE_integer("task_id", 2, "bAbI task id, 1 <= id <= 20")
tf.flags.DEFINE_integer("random_state", None, "Random state.")
tf.flags.DEFINE_string("data_dir", "data/babi-tasks-v1-2/tasks_1-20_v1-2/en-10k/", "Directory containing bAbI tasks")
tf.flags.DEFINE_string("log_dir", "logs", "Directory containing logs")
FLAGS = tf.flags.FLAGS

def train_for_task(task_id):
    if tf.gfile.Exists(FLAGS.log_dir):
        tf.gfile.DeleteRecursively(FLAGS.log_dir)


    tf.gfile.MakeDirs(FLAGS.log_dir)
    # task data
    train, test = load_task(FLAGS.data_dir, task_id)
    data = train + test
    vocab = sorted(reduce(lambda x, y: x | y, (set(list(chain.from_iterable(s)) + q + a) for s, q, a in data)))
    word_idx = dict((c, i + 1) for i, c in enumerate(vocab))
    max_story_size = max(map(len, (s for s, _, _ in data)))
    mean_story_size = int(np.mean([len(s) for s, _, _ in data]))

    sentence_size = max(map(len, chain.from_iterable(s for s, _, _ in data)))
    query_size = max(map(len, (q for _, q, _ in data)))
    memory_size = min(FLAGS.memory_size, max_story_size)
    # Add time words/indexes
    for i in range(memory_size):
        word_idx['time{}'.format(i + 1)] = 'time{}'.format(i + 1)
    vocab_size = len(word_idx) + 1  # +1 for nil word
    sentence_size = max(query_size, sentence_size)  # for the position
    sentence_size += 1  # +1 for time words

    print("Longest sentence length", sentence_size)
    print("Longest story length", max_story_size)
    print("Average story length", mean_story_size)

    # train/validation/test sets
    S, Q, A = vectorize_data(train, word_idx, sentence_size, memory_size)
    trainS, valS, trainQ, valQ, trainA, valA = cross_validation.train_test_split(S, Q, A, test_size=.1,
                                                                                 random_state=FLAGS.random_state)
    testS, testQ, testA = vectorize_data(test, word_idx, sentence_size, memory_size)

    print(testS[0])
    print("Training set shape", trainS.shape)

    # params
    n_train = trainS.shape[0]
    n_test = testS.shape[0]
    n_val = valS.shape[0]

    print("Training Size", n_train)
    print("Validation Size", n_val)
    print("Testing Size", n_test)

    train_labels = np.argmax(trainA, axis=1)
    test_labels = np.argmax(testA, axis=1)
    val_labels = np.argmax(valA, axis=1)
    tf.set_random_seed(FLAGS.random_state)
    batch_size = FLAGS.batch_size
    batches = zip(range(0, n_train - batch_size, batch_size), range(batch_size, n_train, batch_size))
    batches = [(start, end) for start, end in batches]
    with tf.Session() as sess:
        model = MemN2N(batch_size, vocab_size, sentence_size, memory_size, FLAGS.embedding_size, session=sess,
                       hops=FLAGS.hops, max_grad_norm=FLAGS.max_grad_norm)

        # Merge all the summaries and write them out to /tmp/tensorflow/mnist/logs/mnist_with_summaries (by default)
        merged = tf.summary.merge_all()
        train_writer = tf.summary.FileWriter(FLAGS.log_dir + '/train', sess.graph)
        test_writer = tf.summary.FileWriter(FLAGS.log_dir + '/test')
        val_writer = tf.summary.FileWriter(FLAGS.log_dir + '/val')

        for t in range(1, FLAGS.epochs + 1):
            # Stepped learning rate
            if t - 1 <= FLAGS.anneal_stop_epoch:
                anneal = 2.0 ** ((t - 1) // FLAGS.anneal_rate)
            else:
                anneal = 2.0 ** (FLAGS.anneal_stop_epoch // FLAGS.anneal_rate)
            lr = FLAGS.learning_rate / anneal

            np.random.shuffle(batches)
            total_cost = 0.0
            for start, end in batches:
                s = trainS[start:end]
                q = trainQ[start:end]
                a = trainA[start:end]
                cost_t, summary = model.batch_fit(s, q, a, lr, merged)
                total_cost += cost_t

            if t % FLAGS.evaluation_interval == 0:
                train_preds, summary = model.predict(trainS, trainQ, trainA, merged)
                train_writer.add_summary(summary, t)

                val_preds, summary = model.predict(valS, valQ, valA, merged)
                val_writer.add_summary(summary, t)

                train_acc = metrics.accuracy_score(train_preds, train_labels)
                val_acc = metrics.accuracy_score(val_preds, val_labels)

                test_preds, summary = model.predict(testS, testQ, testA, merged)
                test_writer.add_summary(summary, t)

                print('-----------------------')
                print('Epoch', t)
                print('Total Cost:', total_cost)
                print('Training Accuracy:', train_acc)
                print('Validation Accuracy:', val_acc)
                print('-----------------------')

        test_preds, summary = model.predict(testS, testQ, testA, merged)
        test_writer.add_summary(summary, t)
        test_acc = metrics.accuracy_score(test_preds, test_labels)

        train_writer.close()
        test_writer.close()
        val_writer.close()

import sys

#task_id = int(sys.argv[1])
task_id = 10

print("Starting Task:", task_id)
train_for_task(task_id)
