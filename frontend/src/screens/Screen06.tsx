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

const Screen06SearchResults = () => {
  const { navigate } = useAppRouter();
  return (
    <AuthenticatedLayout title="Search Results">
      <div className="flex flex-col md:flex-row gap-8">
        {/* Sidebar Filters */}
        <div className="w-full md:w-64 flex-shrink-0 space-y-6">
          <div>
            <h4 className="font-medium text-sm text-slate-900 mb-3 uppercase tracking-wider">Department</h4>
            <div className="space-y-2">
              {['All', 'Computer Science', 'Agriculture', 'Economics'].map(dept => (
                <label key={dept} className="flex items-center text-sm text-slate-600">
                  <input type="checkbox" className="mr-2 rounded border-slate-300 text-[#00502F] focus:ring-[#00502F]" defaultChecked={dept === 'All'} /> {dept}
                </label>
              ))}
            </div>
          </div>
          <div>
            <h4 className="font-medium text-sm text-slate-900 mb-3 uppercase tracking-wider">Year</h4>
            <select className="w-full border-slate-300 rounded-md text-sm p-2 bg-white">
              <option>Any Year</option>
              <option>2024</option>
              <option>2023</option>
            </select>
          </div>
        </div>

        {/* Results */}
        <div className="flex-1">
          <div className="mb-6 flex justify-between items-center border-b border-slate-200 pb-4">
            <p className="text-sm text-slate-600">Showing <strong>24</strong> results for <span className="font-medium text-slate-900">"machine learning agriculture"</span></p>
            <div className="flex items-center space-x-2 text-sm">
              <span className="text-slate-500">Sort by:</span>
              <select className="border-none bg-transparent font-medium text-slate-900 focus:ring-0 cursor-pointer">
                <option>Relevance</option>
                <option>Newest</option>
                <option>Citations</option>
              </select>
            </div>
          </div>
          
          <div className="space-y-4">
            {MOCK_THESES.slice(0, 3).map((thesis, i) => (
              <Card key={thesis.id} hover className="p-6 flex flex-col md:flex-row gap-6 items-start" onClick={() => navigate('thesis-detail')}>
                <div className="flex-1">
                  <div className="flex items-center space-x-2 mb-1">
                    <span className="text-xs font-semibold text-[#00502F] bg-emerald-50 px-2 py-0.5 rounded">{i === 0 ? '98% Match' : '85% Match'}</span>
                    <span className="text-xs text-slate-400">{thesis.year}</span>
                  </div>
                  <h3 className="text-lg font-bold text-slate-900 mb-1">{thesis.title}</h3>
                  <p className="text-sm text-[#D4AF37] mb-3">{thesis.author} • {thesis.dept}</p>
                  <p className="text-sm text-slate-600 mb-4">{thesis.abstract}</p>
                  <div className="flex items-center space-x-3">
                    {thesis.tags.map(tag => (
                      <span key={tag} className="text-xs text-slate-500 bg-slate-100 px-2 py-1 rounded">{tag}</span>
                    ))}
                  </div>
                </div>
                <div className="md:w-32 flex flex-col space-y-2">
                  <Button variant="secondary" className="w-full text-xs" onClick={(e) => { e.stopPropagation(); navigate('pdf-reader'); }}>Read PDF</Button>
                  <Button variant="ghost" className="w-full text-xs" onClick={(e) => { e.stopPropagation(); navigate('saved'); }}>Save</Button>
                </div>
              </Card>
            ))}
          </div>
        </div>
      </div>
    </AuthenticatedLayout>
  );
};

export default Screen06SearchResults;
