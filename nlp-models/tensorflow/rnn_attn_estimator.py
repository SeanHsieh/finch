import tensorflow as tf
import numpy as np
tf.logging.set_verbosity(tf.logging.INFO)


class Estimator:
    def __init__(self, vocab_size, n_out, embedding_dims=128, rnn_size=128, dropout_rate=0.2, grad_clip=5.0,
                 attn_size=50):
        self.vocab_size = vocab_size
        self.n_out = n_out
        self.embedding_dims = embedding_dims
        self.rnn_size = rnn_size
        self.dropout_rate = dropout_rate
        self.grad_clip = grad_clip
        self.attn_size = attn_size
        self.model = tf.estimator.Estimator(self.model_fn)
    # end constructor


    def forward_pass(self, x, seq_len, reuse, dropout_rate):
        with tf.variable_scope('forward_pass', reuse=reuse):
            embedded = tf.nn.dropout(
                tf.contrib.layers.embed_sequence(
                    x, self.vocab_size, self.embedding_dims, scope='word_embedding', reuse=reuse),
                        (1-dropout_rate))

            with tf.variable_scope('rnn', reuse=reuse):
                cell = tf.nn.rnn_cell.LSTMCell(self.rnn_size, initializer=tf.orthogonal_initializer())
                rnn_out, final_state = tf.nn.dynamic_rnn(
                    cell, embedded, sequence_length=seq_len, dtype=tf.float32)

            with tf.variable_scope('attention', reuse=reuse):
                weights = tf.nn.softmax(tf.squeeze(tf.matmul(
                    rnn_out, tf.expand_dims(final_state.h,2)), 2))
                weighted_sum = tf.squeeze(tf.matmul(
                    tf.transpose(rnn_out,[0,2,1]), tf.expand_dims(weights,2)), 2)

            with tf.variable_scope('output_layer', reuse=reuse):
                logits = tf.layers.dense(weighted_sum, self.n_out)
        return logits
    # end method


    def model_fn(self, features, labels, mode):
        if mode == tf.estimator.ModeKeys.TRAIN or mode == tf.estimator.ModeKeys.PREDICT:
            logits = self.forward_pass(
                features['data'], features['data_len'], reuse=False, dropout_rate=self.dropout_rate)
        
        if mode == tf.estimator.ModeKeys.TRAIN:
            logits_val = self.forward_pass(
                features['data_val'], features['data_val_len'], reuse=True, dropout_rate=0.0)
            
        if mode == tf.estimator.ModeKeys.PREDICT:
            predictions = tf.argmax(self.forward_pass(
                features['data'], features['data_len'], reuse=True, dropout_rate=0.0), axis=1)
            return tf.estimator.EstimatorSpec(mode, predictions=predictions)

        if mode == tf.estimator.ModeKeys.TRAIN:
            with tf.name_scope('back_propagation'):
                loss_op = tf.reduce_mean(tf.nn.sparse_softmax_cross_entropy_with_logits(
                    logits=logits, labels=labels))
                loss_val_op = tf.reduce_mean(tf.nn.sparse_softmax_cross_entropy_with_logits(
                    logits=logits_val, labels=features['labels_val']))
                tf.summary.scalar('loss', loss_op)
                tf.summary.scalar('val_loss', loss_val_op)

                acc_op = tf.reduce_mean(tf.cast(tf.equal(tf.argmax(logits,1), labels), tf.float32))
                acc_val_op = tf.reduce_mean(tf.cast(tf.equal(
                    tf.argmax(logits_val,1), features['labels_val']), tf.float32))
                tf.summary.scalar('acc', acc_op)
                tf.summary.scalar('val_acc', acc_val_op)

                tensor_hook = tf.train.LoggingTensorHook(
                    {'loss_val':loss_val_op, 'acc':acc_op, 'acc_val':acc_val_op}, every_n_iter=100)

                params = tf.trainable_variables()
                gradients = tf.gradients(loss_op, params)
                clipped_gradients, _ = tf.clip_by_global_norm(gradients, self.grad_clip)
                train_op = tf.train.AdamOptimizer().apply_gradients(
                    zip(clipped_gradients, params), global_step=tf.train.get_global_step())

                summary_hook = tf.train.SummarySaverHook(
                    save_steps=10, output_dir='./board/', summary_op=tf.summary.merge_all())

            return tf.estimator.EstimatorSpec(
                mode=mode,
                loss=loss_op,
                train_op=train_op,
                training_hooks = [tensor_hook, summary_hook])
    # end method


    def fit(self, X_train, X_train_len, y_train, X_test, X_test_len, y_test, batch_size=128, n_epoch=10):
        input_fn = tf.estimator.inputs.numpy_input_fn(
            x={'data':X_train, 'data_len':X_train_len, 'data_val':X_test, 'data_val_len':X_test_len,
               'labels_val':y_test},
            y=y_train, batch_size=batch_size, num_epochs=n_epoch, shuffle=True)
        self.model.train(input_fn)
    # end method


    def predict(self, X_test, X_test_len, batch_size=128):
        input_fn = tf.estimator.inputs.numpy_input_fn(
            x={'data': X_test, 'data_len':X_test_len}, batch_size=batch_size, shuffle=False)
        return np.array(list(self.model.predict(input_fn)))
    # end method


    def _softmax(self, tensor):
        exps = tf.exp(tensor)
        return exps / tf.reduce_sum(exps, 1, keep_dims=True)
    # end method softmax
# end class