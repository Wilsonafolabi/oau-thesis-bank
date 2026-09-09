import React, { useState, useEffect, useContext, createContext } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search, BookOpen, Users, Cpu, FileText, ChevronRight, Lock, Unlock, Mail, Settings,
  LogOut, Bell, MessageSquare, Activity, BarChart2, PlusCircle, CheckCircle, AlertTriangle,
  Download, Bookmark, Share2, Filter, MoreVertical, X, Menu, Home, Grid, Lightbulb,
  FileSearch, UserPlus, Shield, Check, FileUp, Database, GitBranch, ArrowRight, ArrowLeft,
  MessageCircle, Link as LinkIcon, ThumbsUp, Send, PieChart, TrendingUp, Search as SearchIcon,
  ShieldAlert, Settings2, Sliders, ChevronDown, Book, User, Calendar
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, PieChart as RePieChart, Pie, Cell, AreaChart, Area
} from 'recharts';
import {
  theme, MOCK_THESES, MOCK_USERS, MOCK_MESSAGES, useAppRouter,
  Button, Input, Card, Badge, PublicLayout, AuthenticatedLayout, AuthContainer,
  ThesisCard, UploadWizardNav, pageVariants, listVariants, itemVariants
} from '../components/shared';

const Screen12ThesisDiscussion = () => {
  const { navigate } = useAppRouter();
  return (
    <AuthenticatedLayout title="Thesis Discussion">
      <div className="max-w-4xl mx-auto">
        <div className="mb-6">
          <h2 className="text-xl font-bold text-slate-900">Machine Learning for Crop Yield Prediction</h2>
          <button className="text-sm text-[#00502F] hover:underline" onClick={() => navigate('thesis-detail')}>Back to Thesis</button>
        </div>

        <Card className="p-6 mb-8 bg-slate-50 border-dashed">
          <textarea placeholder="Start a new discussion thread..." className="w-full bg-white border border-slate-300 p-3 rounded-md focus:outline-none focus:ring-1 focus:ring-[#00502F] text-sm resize-none h-24"></textarea>
          <div className="mt-3 flex justify-end">
            <Button>Post Discussion</Button>
          </div>
        </Card>

        <div className="space-y-6">
          {[1, 2].map(thread => (
            <div key={thread} className="bg-white p-6 rounded-lg border border-slate-200">
              <div className="flex items-start space-x-4">
                <div className="w-10 h-10 rounded-full bg-slate-200 flex items-center justify-center font-bold text-slate-500">
                  {thread === 1 ? 'EA' : 'OF'}
                </div>
                <div className="flex-1">
                  <div className="flex justify-between items-baseline mb-1">
                    <h4 className="font-medium text-slate-900">{thread === 1 ? 'Prof. E. Adagunodo' : 'Dr. O. Fajemisin'}</h4>
                    <span className="text-xs text-slate-500">2 days ago</span>
                  </div>
                  <p className="text-sm text-slate-700 mb-3">
                    {thread === 1 
                      ? "The approach to handling missing data in the NIMET dataset is quite innovative. Could you clarify if imputation was done before or after the train/test split?" 
                      : "I suggest looking into the related work by Adeyemi et al. (2021) for comparison in your future work section."}
                  </p>
                  <div className="flex items-center space-x-4 text-xs text-slate-500 font-medium">
                    <button className="flex items-center hover:text-[#00502F]"><ThumbsUp className="w-3 h-3 mr-1"/> Helpful (2)</button>
                    <button className="flex items-center hover:text-[#00502F]"><MessageCircle className="w-3 h-3 mr-1"/> Reply</button>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen12ThesisDiscussion;
